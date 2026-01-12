"""Strategy Comparison Dashboard.

Compare validated trading strategies by Sharpe ratio, drawdown, p-value,
and other metrics to identify the best performing strategies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
import json
import logging

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class StrategyComparison:
    """Comparison data for a validated strategy."""

    strategy_name: str
    symbol: str

    # Core metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0  # Expressed as positive percentage
    total_return: float = 0.0

    # Validation
    mcpt_p_value: Optional[float] = None
    validated: bool = False
    validation_date: Optional[datetime] = None

    # Trade statistics
    win_rate: float = 0.0
    profit_factor: float = 0.0
    num_trades: int = 0
    avg_trade_return: float = 0.0

    # Risk metrics
    volatility: float = 0.0
    calmar_ratio: float = 0.0  # Annual return / max drawdown
    var_95: float = 0.0  # 95% Value at Risk

    # Hold period
    avg_hold_days: float = 0.0

    # Additional context
    backtest_start: Optional[datetime] = None
    backtest_end: Optional[datetime] = None
    notes: str = ""

    @property
    def is_mcpt_validated(self) -> bool:
        """Check if strategy passes MCPT validation (p < 0.05)."""
        if self.mcpt_p_value is None:
            return False
        return self.mcpt_p_value < 0.05

    @property
    def quality_score(self) -> float:
        """Composite quality score combining multiple metrics.

        Higher is better. Weights:
        - Sharpe ratio: 30%
        - MCPT significance: 25%
        - Win rate: 20%
        - Max drawdown (inverse): 15%
        - Profit factor: 10%
        """
        score = 0.0

        # Sharpe contribution (capped at 5 for normalization)
        sharpe_normalized = min(self.sharpe_ratio / 5.0, 1.0) if self.sharpe_ratio > 0 else 0
        score += 0.30 * sharpe_normalized

        # MCPT significance contribution (lower p-value = higher score)
        if self.mcpt_p_value is not None:
            mcpt_normalized = max(0, 1 - (self.mcpt_p_value / 0.10))  # 0.10 as baseline
            score += 0.25 * mcpt_normalized

        # Win rate contribution
        score += 0.20 * self.win_rate

        # Drawdown contribution (lower is better, capped at 30%)
        dd_normalized = max(0, 1 - (self.max_drawdown / 30.0))
        score += 0.15 * dd_normalized

        # Profit factor contribution (capped at 3.0)
        pf_normalized = min(self.profit_factor / 3.0, 1.0) if self.profit_factor > 0 else 0
        score += 0.10 * pf_normalized

        return score

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "total_return": self.total_return,
            "mcpt_p_value": self.mcpt_p_value,
            "validated": self.validated,
            "validation_date": self.validation_date.isoformat() if self.validation_date else None,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "num_trades": self.num_trades,
            "avg_trade_return": self.avg_trade_return,
            "volatility": self.volatility,
            "calmar_ratio": self.calmar_ratio,
            "var_95": self.var_95,
            "avg_hold_days": self.avg_hold_days,
            "backtest_start": self.backtest_start.isoformat() if self.backtest_start else None,
            "backtest_end": self.backtest_end.isoformat() if self.backtest_end else None,
            "quality_score": self.quality_score,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyComparison":
        """Create from dictionary."""
        return cls(
            strategy_name=data["strategy_name"],
            symbol=data["symbol"],
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            sortino_ratio=data.get("sortino_ratio", 0.0),
            max_drawdown=data.get("max_drawdown", 0.0),
            total_return=data.get("total_return", 0.0),
            mcpt_p_value=data.get("mcpt_p_value"),
            validated=data.get("validated", False),
            validation_date=datetime.fromisoformat(data["validation_date"]) if data.get("validation_date") else None,
            win_rate=data.get("win_rate", 0.0),
            profit_factor=data.get("profit_factor", 0.0),
            num_trades=data.get("num_trades", 0),
            avg_trade_return=data.get("avg_trade_return", 0.0),
            volatility=data.get("volatility", 0.0),
            calmar_ratio=data.get("calmar_ratio", 0.0),
            var_95=data.get("var_95", 0.0),
            avg_hold_days=data.get("avg_hold_days", 0.0),
            backtest_start=datetime.fromisoformat(data["backtest_start"]) if data.get("backtest_start") else None,
            backtest_end=datetime.fromisoformat(data["backtest_end"]) if data.get("backtest_end") else None,
            notes=data.get("notes", ""),
        )


class StrategyDashboard:
    """
    Dashboard for comparing and ranking trading strategies.

    Loads strategy validation results from:
    1. A validated_strategies.yaml config file
    2. Individual validation result JSON files

    Provides ranking, filtering, and reporting capabilities.
    """

    def __init__(
        self,
        validated_strategies_path: Optional[Path] = None,
        validation_results_dir: Optional[Path] = None,
    ):
        """Initialize the dashboard.

        Args:
            validated_strategies_path: Path to validated_strategies.yaml
            validation_results_dir: Directory with validation result JSON files
        """
        self.strategies_path = validated_strategies_path or (paths.base / "config" / "validated_strategies.yaml")
        self.results_dir = validation_results_dir or (paths.results / "validation")
        self._cache: list[StrategyComparison] = []
        self._cache_loaded = False

    def load_comparisons(self, force_reload: bool = False) -> list[StrategyComparison]:
        """Load all validated strategy results.

        Args:
            force_reload: Force reload from files even if cached

        Returns:
            List of StrategyComparison objects
        """
        if self._cache_loaded and not force_reload:
            return self._cache

        comparisons = []

        # Load from YAML config if exists
        if self.strategies_path.exists():
            comparisons.extend(self._load_from_yaml())

        # Load from validation results directory
        if self.results_dir.exists():
            comparisons.extend(self._load_from_results_dir())

        # Deduplicate by (strategy_name, symbol)
        seen = set()
        unique_comparisons = []
        for c in comparisons:
            key = (c.strategy_name, c.symbol)
            if key not in seen:
                seen.add(key)
                unique_comparisons.append(c)

        self._cache = unique_comparisons
        self._cache_loaded = True

        logger.info(f"Loaded {len(unique_comparisons)} strategy comparisons")
        return unique_comparisons

    def _load_from_yaml(self) -> list[StrategyComparison]:
        """Load comparisons from validated_strategies.yaml."""
        comparisons = []

        try:
            with open(self.strategies_path, "r") as f:
                if HAS_YAML:
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)

            if not data:
                return []

            for strategy, symbols in data.items():
                if not isinstance(symbols, dict):
                    continue

                for symbol, metrics in symbols.items():
                    if not isinstance(metrics, dict):
                        continue

                    comparison = StrategyComparison(
                        strategy_name=strategy,
                        symbol=symbol,
                        sharpe_ratio=metrics.get("sharpe", metrics.get("sharpe_ratio", 0.0)),
                        sortino_ratio=metrics.get("sortino", metrics.get("sortino_ratio", 0.0)),
                        max_drawdown=metrics.get("max_drawdown", 0.0),
                        total_return=metrics.get("total_return", 0.0),
                        mcpt_p_value=metrics.get("p_value", metrics.get("mcpt_p_value")),
                        validated=metrics.get("validated", False),
                        win_rate=metrics.get("win_rate", 0.0),
                        profit_factor=metrics.get("profit_factor", 0.0),
                        num_trades=metrics.get("num_trades", 0),
                    )

                    # Parse validation date if present
                    if "validation_date" in metrics:
                        try:
                            comparison.validation_date = datetime.fromisoformat(metrics["validation_date"])
                        except (ValueError, TypeError):
                            pass

                    comparisons.append(comparison)

        except Exception as e:
            logger.error(f"Error loading from {self.strategies_path}: {e}")

        return comparisons

    def _load_from_results_dir(self) -> list[StrategyComparison]:
        """Load comparisons from validation result JSON files."""
        comparisons = []

        if not self.results_dir.exists():
            return []

        for filepath in self.results_dir.glob("**/*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)

                # Handle different result formats
                if "strategy_name" in data:
                    comparison = self._parse_validation_result(data)
                    if comparison:
                        comparisons.append(comparison)
                elif "results" in data:
                    # Batch result file
                    for result in data["results"]:
                        comparison = self._parse_validation_result(result)
                        if comparison:
                            comparisons.append(comparison)

            except Exception as e:
                logger.debug(f"Skipping {filepath}: {e}")

        return comparisons

    def _parse_validation_result(self, data: dict) -> Optional[StrategyComparison]:
        """Parse a validation result dict into StrategyComparison."""
        try:
            strategy_name = data.get("strategy_name", "unknown")
            symbol = data.get("symbol", "")

            if not symbol:
                return None

            # Extract metrics from various possible locations
            original_metrics = data.get("original_metrics", {})
            p_values = data.get("p_values", {})

            comparison = StrategyComparison(
                strategy_name=strategy_name,
                symbol=symbol,
                sharpe_ratio=original_metrics.get("sharpe", 0.0),
                sortino_ratio=original_metrics.get("sortino", 0.0),
                max_drawdown=abs(original_metrics.get("max_drawdown", 0.0)),
                total_return=original_metrics.get("total_return", 0.0),
                mcpt_p_value=p_values.get("sharpe"),
                validated=data.get("is_significant", {}).get("sharpe", False),
                win_rate=original_metrics.get("win_rate", 0.0),
                profit_factor=original_metrics.get("profit_factor", 0.0),
                num_trades=original_metrics.get("n_trades", 0),
            )

            # Parse timestamp
            if "timestamp" in data:
                try:
                    comparison.validation_date = datetime.fromisoformat(data["timestamp"])
                except (ValueError, TypeError):
                    pass

            return comparison

        except Exception as e:
            logger.debug(f"Failed to parse validation result: {e}")
            return None

    def rank_by_metric(
        self,
        metric: str = "sharpe_ratio",
        ascending: bool = False,
    ) -> list[StrategyComparison]:
        """Rank strategies by a specific metric.

        Args:
            metric: Metric to rank by (sharpe_ratio, sortino_ratio, max_drawdown,
                   total_return, win_rate, profit_factor, quality_score, mcpt_p_value)
            ascending: If True, rank from lowest to highest

        Returns:
            List of StrategyComparison sorted by metric
        """
        comparisons = self.load_comparisons()

        def get_metric_value(c: StrategyComparison) -> float:
            value = getattr(c, metric, 0)
            if value is None:
                return float('-inf') if not ascending else float('inf')
            return value

        return sorted(comparisons, key=get_metric_value, reverse=not ascending)

    def get_validated_only(self) -> list[StrategyComparison]:
        """Get only MCPT-validated strategies (p < 0.05).

        Returns:
            List of validated strategies sorted by Sharpe ratio
        """
        comparisons = self.load_comparisons()
        validated = [c for c in comparisons if c.is_mcpt_validated]
        return sorted(validated, key=lambda x: x.sharpe_ratio, reverse=True)

    def get_top_performers(
        self,
        n: int = 10,
        metric: str = "quality_score",
        validated_only: bool = True,
    ) -> list[StrategyComparison]:
        """Get top N performing strategies.

        Args:
            n: Number of strategies to return
            metric: Metric to rank by
            validated_only: Only include MCPT-validated strategies

        Returns:
            Top N strategies by the specified metric
        """
        if validated_only:
            comparisons = self.get_validated_only()
        else:
            comparisons = self.load_comparisons()

        ranked = sorted(
            comparisons,
            key=lambda x: getattr(x, metric, 0) or 0,
            reverse=True
        )
        return ranked[:n]

    def filter_by_criteria(
        self,
        min_sharpe: Optional[float] = None,
        max_p_value: Optional[float] = None,
        min_win_rate: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        symbols: Optional[list[str]] = None,
        strategies: Optional[list[str]] = None,
    ) -> list[StrategyComparison]:
        """Filter strategies by multiple criteria.

        Args:
            min_sharpe: Minimum Sharpe ratio
            max_p_value: Maximum MCPT p-value
            min_win_rate: Minimum win rate (0-1)
            max_drawdown: Maximum drawdown percentage
            symbols: List of symbols to include
            strategies: List of strategy names to include

        Returns:
            Filtered list of strategies
        """
        comparisons = self.load_comparisons()
        filtered = []

        for c in comparisons:
            if min_sharpe is not None and c.sharpe_ratio < min_sharpe:
                continue
            if max_p_value is not None and (c.mcpt_p_value is None or c.mcpt_p_value > max_p_value):
                continue
            if min_win_rate is not None and c.win_rate < min_win_rate:
                continue
            if max_drawdown is not None and c.max_drawdown > max_drawdown:
                continue
            if symbols is not None and c.symbol not in symbols:
                continue
            if strategies is not None and c.strategy_name not in strategies:
                continue
            filtered.append(c)

        return sorted(filtered, key=lambda x: x.sharpe_ratio, reverse=True)

    def get_by_symbol(self, symbol: str) -> list[StrategyComparison]:
        """Get all strategies for a specific symbol.

        Args:
            symbol: Symbol to filter by

        Returns:
            List of strategies for that symbol, sorted by Sharpe
        """
        comparisons = self.load_comparisons()
        matching = [c for c in comparisons if c.symbol == symbol]
        return sorted(matching, key=lambda x: x.sharpe_ratio, reverse=True)

    def get_by_strategy(self, strategy_name: str) -> list[StrategyComparison]:
        """Get all symbols for a specific strategy.

        Args:
            strategy_name: Strategy name to filter by

        Returns:
            List of symbol results for that strategy, sorted by Sharpe
        """
        comparisons = self.load_comparisons()
        matching = [c for c in comparisons if c.strategy_name == strategy_name]
        return sorted(matching, key=lambda x: x.sharpe_ratio, reverse=True)

    def generate_report(self, include_all: bool = False) -> str:
        """Generate markdown comparison report.

        Args:
            include_all: Include non-validated strategies

        Returns:
            Markdown formatted report
        """
        if include_all:
            comparisons = self.load_comparisons()
        else:
            comparisons = self.get_validated_only()

        if not comparisons:
            return "# Strategy Comparison Report\n\nNo strategies found."

        lines = [
            "# Strategy Comparison Report",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        # Summary stats
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Total strategies: {len(comparisons)}")
        validated_count = sum(1 for c in comparisons if c.is_mcpt_validated)
        lines.append(f"- MCPT validated (p < 0.05): {validated_count}")

        if comparisons:
            avg_sharpe = sum(c.sharpe_ratio for c in comparisons) / len(comparisons)
            lines.append(f"- Average Sharpe ratio: {avg_sharpe:.2f}")

        lines.append("")

        # Top performers by quality score
        lines.append("## Top Strategies by Quality Score")
        lines.append("")
        lines.append("| Rank | Strategy | Symbol | Sharpe | Drawdown | p-value | Win Rate | Score |")
        lines.append("|------|----------|--------|--------|----------|---------|----------|-------|")

        top_by_quality = sorted(comparisons, key=lambda x: x.quality_score, reverse=True)[:10]
        for i, s in enumerate(top_by_quality, 1):
            p_str = f"{s.mcpt_p_value:.3f}" if s.mcpt_p_value is not None else "N/A"
            lines.append(
                f"| {i} | {s.strategy_name[:20]} | {s.symbol} | {s.sharpe_ratio:.2f} | "
                f"{s.max_drawdown:.1f}% | {p_str} | {s.win_rate:.0%} | {s.quality_score:.2f} |"
            )

        lines.append("")

        # Validated strategies table
        validated = [c for c in comparisons if c.is_mcpt_validated]
        if validated:
            lines.append("## MCPT Validated Strategies (p < 0.05)")
            lines.append("")
            lines.append("| Strategy | Symbol | Sharpe | Sortino | Drawdown | p-value |")
            lines.append("|----------|--------|--------|---------|----------|---------|")

            for s in sorted(validated, key=lambda x: x.sharpe_ratio, reverse=True):
                lines.append(
                    f"| {s.strategy_name} | {s.symbol} | {s.sharpe_ratio:.2f} | "
                    f"{s.sortino_ratio:.2f} | {s.max_drawdown:.1f}% | {s.mcpt_p_value:.3f} |"
                )

            lines.append("")

        # By strategy summary
        lines.append("## Performance by Strategy Type")
        lines.append("")

        strategy_groups: dict[str, list[StrategyComparison]] = {}
        for c in comparisons:
            if c.strategy_name not in strategy_groups:
                strategy_groups[c.strategy_name] = []
            strategy_groups[c.strategy_name].append(c)

        lines.append("| Strategy | Symbols | Avg Sharpe | Best Symbol | Best Sharpe |")
        lines.append("|----------|---------|------------|-------------|-------------|")

        for strategy, items in sorted(strategy_groups.items()):
            avg_sharpe = sum(c.sharpe_ratio for c in items) / len(items)
            best = max(items, key=lambda x: x.sharpe_ratio)
            lines.append(
                f"| {strategy} | {len(items)} | {avg_sharpe:.2f} | {best.symbol} | {best.sharpe_ratio:.2f} |"
            )

        return "\n".join(lines)

    def save_validated_strategies(
        self,
        output_path: Optional[Path] = None,
    ) -> Path:
        """Save validated strategies to YAML/JSON file.

        Args:
            output_path: Output path (defaults to config/validated_strategies.yaml)

        Returns:
            Path where file was saved
        """
        output_path = output_path or self.strategies_path

        # Build structure: strategy -> symbol -> metrics
        data: dict[str, dict[str, dict]] = {}

        for c in self.get_validated_only():
            if c.strategy_name not in data:
                data[c.strategy_name] = {}

            data[c.strategy_name][c.symbol] = {
                "sharpe": c.sharpe_ratio,
                "sortino": c.sortino_ratio,
                "max_drawdown": c.max_drawdown,
                "p_value": c.mcpt_p_value,
                "validated": c.is_mcpt_validated,
                "win_rate": c.win_rate,
                "num_trades": c.num_trades,
                "validation_date": c.validation_date.isoformat() if c.validation_date else None,
            }

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            if HAS_YAML and output_path.suffix == ".yaml":
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            else:
                json.dump(data, f, indent=2)

        logger.info(f"Saved validated strategies to {output_path}")
        return output_path

    def add_comparison(self, comparison: StrategyComparison) -> None:
        """Add a new comparison to the cache.

        Args:
            comparison: StrategyComparison to add
        """
        self.load_comparisons()  # Ensure cache is loaded

        # Remove existing entry if present
        self._cache = [c for c in self._cache
                      if not (c.strategy_name == comparison.strategy_name and
                              c.symbol == comparison.symbol)]

        self._cache.append(comparison)

    def get_summary(self) -> dict[str, Any]:
        """Get dashboard summary statistics.

        Returns:
            Summary dict
        """
        comparisons = self.load_comparisons()

        if not comparisons:
            return {
                "total_strategies": 0,
                "validated_count": 0,
                "unique_symbols": 0,
            }

        validated = [c for c in comparisons if c.is_mcpt_validated]
        symbols = set(c.symbol for c in comparisons)
        strategy_names = set(c.strategy_name for c in comparisons)

        return {
            "total_strategies": len(comparisons),
            "validated_count": len(validated),
            "unique_symbols": len(symbols),
            "unique_strategy_types": len(strategy_names),
            "avg_sharpe": sum(c.sharpe_ratio for c in comparisons) / len(comparisons),
            "best_sharpe": max(c.sharpe_ratio for c in comparisons),
            "avg_validated_sharpe": sum(c.sharpe_ratio for c in validated) / len(validated) if validated else 0,
        }


def get_strategy_leaderboard(top_n: int = 10, validated_only: bool = True) -> str:
    """Quick utility to get strategy leaderboard.

    Args:
        top_n: Number of strategies to show
        validated_only: Only include validated strategies

    Returns:
        Markdown formatted leaderboard
    """
    dashboard = StrategyDashboard()
    top = dashboard.get_top_performers(n=top_n, validated_only=validated_only)

    if not top:
        return "No strategies found."

    lines = [
        "# Strategy Leaderboard",
        "",
        f"Top {len(top)} {'validated ' if validated_only else ''}strategies by quality score:",
        "",
        "| Rank | Strategy | Symbol | Sharpe | p-value | Score |",
        "|------|----------|--------|--------|---------|-------|",
    ]

    for i, s in enumerate(top, 1):
        p_str = f"{s.mcpt_p_value:.3f}" if s.mcpt_p_value is not None else "N/A"
        lines.append(
            f"| {i} | {s.strategy_name} | {s.symbol} | {s.sharpe_ratio:.2f} | {p_str} | {s.quality_score:.2f} |"
        )

    return "\n".join(lines)
