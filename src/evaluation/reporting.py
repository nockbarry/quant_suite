"""Report generation for strategy evaluation.

Generates comprehensive HTML and PDF reports for:
- Backtest results
- Strategy comparisons
- Performance monitoring
- Statistical analysis
"""

import base64
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Try to import plotting libraries
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.info("matplotlib not available, charts disabled")


@dataclass
class ReportConfig:
    """Report configuration."""

    title: str = "Strategy Report"
    author: str = "Quant Suite"
    include_charts: bool = True
    include_trades: bool = True
    include_statistics: bool = True
    chart_style: str = "seaborn"
    date_format: str = "%Y-%m-%d"


class ChartGenerator:
    """Generate charts for reports."""

    def __init__(self, style: str = "seaborn"):
        """Initialize chart generator."""
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib not available, charts will be skipped")
            return

        plt.style.use("seaborn-v0_8-whitegrid")
        self.fig_size = (10, 6)
        self.colors = {
            "primary": "#2563eb",
            "secondary": "#64748b",
            "positive": "#22c55e",
            "negative": "#ef4444",
            "neutral": "#f59e0b",
        }

    def equity_curve(
        self,
        equity: pd.Series,
        benchmark: pd.Series | None = None,
        title: str = "Equity Curve",
    ) -> str | None:
        """Generate equity curve chart."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=self.fig_size)

        ax.plot(equity.index, equity.values, label="Strategy", color=self.colors["primary"], linewidth=1.5)

        if benchmark is not None:
            ax.plot(benchmark.index, benchmark.values, label="Benchmark",
                   color=self.colors["secondary"], linewidth=1.5, linestyle="--")

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Equity ($)")
        ax.legend()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def drawdown_chart(
        self,
        returns: pd.Series,
        title: str = "Drawdown",
    ) -> str | None:
        """Generate drawdown chart."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        # Calculate drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max * 100

        fig, ax = plt.subplots(figsize=self.fig_size)

        ax.fill_between(drawdown.index, drawdown.values, 0,
                       color=self.colors["negative"], alpha=0.3)
        ax.plot(drawdown.index, drawdown.values, color=self.colors["negative"], linewidth=1)

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Date")
        ax.set_ylabel("Drawdown (%)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def returns_distribution(
        self,
        returns: pd.Series,
        title: str = "Returns Distribution",
    ) -> str | None:
        """Generate returns distribution histogram."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=self.fig_size)

        # Histogram
        n, bins, patches = ax.hist(returns * 100, bins=50, density=True,
                                   alpha=0.7, color=self.colors["primary"])

        # Color positive/negative
        for patch, b in zip(patches, bins[:-1]):
            if b < 0:
                patch.set_facecolor(self.colors["negative"])

        ax.axvline(x=0, color="black", linestyle="--", linewidth=1)
        ax.axvline(x=returns.mean() * 100, color=self.colors["positive"],
                  linestyle="-", linewidth=2, label=f"Mean: {returns.mean()*100:.2f}%")

        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xlabel("Daily Return (%)")
        ax.set_ylabel("Density")
        ax.legend()

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def monthly_returns_heatmap(
        self,
        returns: pd.Series,
        title: str = "Monthly Returns (%)",
    ) -> str | None:
        """Generate monthly returns heatmap."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        # Calculate monthly returns
        monthly = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1) * 100

        # Pivot to year x month
        df = pd.DataFrame({
            "year": monthly.index.year,
            "month": monthly.index.month,
            "return": monthly.values,
        })
        pivot = df.pivot(index="year", columns="month", values="return")

        fig, ax = plt.subplots(figsize=(12, 6))

        # Create heatmap
        im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-10, vmax=10)

        # Labels
        ax.set_xticks(np.arange(12))
        ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        ax.set_yticks(np.arange(len(pivot.index)))
        ax.set_yticklabels(pivot.index)

        # Add text annotations
        for i in range(len(pivot.index)):
            for j in range(12):
                if j < len(pivot.columns) and not np.isnan(pivot.values[i, j]):
                    text = ax.text(j, i, f"{pivot.values[i, j]:.1f}",
                                  ha="center", va="center", fontsize=8)

        ax.set_title(title, fontsize=14, fontweight="bold")
        fig.colorbar(im, ax=ax, label="Return (%)")

        plt.tight_layout()
        return self._fig_to_base64(fig)

    def rolling_metrics(
        self,
        returns: pd.Series,
        window: int = 60,
        title: str = "Rolling Metrics",
    ) -> str | None:
        """Generate rolling metrics chart."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

        # Rolling Sharpe
        rolling_mean = returns.rolling(window).mean()
        rolling_std = returns.rolling(window).std()
        rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(252)

        axes[0].plot(rolling_sharpe.index, rolling_sharpe.values,
                    color=self.colors["primary"], linewidth=1)
        axes[0].axhline(y=0, color="black", linestyle="--", linewidth=0.5)
        axes[0].axhline(y=1, color=self.colors["positive"], linestyle="--", linewidth=0.5)
        axes[0].set_title(f"{window}-Day Rolling Sharpe Ratio", fontsize=12)
        axes[0].set_ylabel("Sharpe Ratio")

        # Rolling volatility
        rolling_vol = rolling_std * np.sqrt(252) * 100

        axes[1].plot(rolling_vol.index, rolling_vol.values,
                    color=self.colors["secondary"], linewidth=1)
        axes[1].fill_between(rolling_vol.index, rolling_vol.values, 0,
                            alpha=0.3, color=self.colors["secondary"])
        axes[1].set_title(f"{window}-Day Rolling Volatility", fontsize=12)
        axes[1].set_ylabel("Volatility (%)")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

        plt.suptitle(title, fontsize=14, fontweight="bold")
        plt.tight_layout()
        return self._fig_to_base64(fig)

    def _fig_to_base64(self, fig) -> str:
        """Convert matplotlib figure to base64 string."""
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close(fig)
        return f"data:image/png;base64,{image_base64}"


class HTMLReportGenerator:
    """Generate HTML reports."""

    def __init__(self, config: ReportConfig | None = None):
        """Initialize report generator."""
        self.config = config or ReportConfig()
        self.chart_gen = ChartGenerator(self.config.chart_style)

    def generate_backtest_report(
        self,
        result: dict[str, Any],
        returns: pd.Series,
        equity: pd.Series | None = None,
        benchmark_returns: pd.Series | None = None,
    ) -> str:
        """
        Generate comprehensive backtest report.

        Args:
            result: Backtest result dictionary
            returns: Strategy returns series
            equity: Equity curve (optional)
            benchmark_returns: Benchmark returns (optional)

        Returns:
            HTML string
        """
        sections = []

        # Header
        sections.append(self._generate_header())

        # Summary section
        sections.append(self._generate_summary_section(result))

        # Charts section
        if self.config.include_charts and MATPLOTLIB_AVAILABLE:
            sections.append(self._generate_charts_section(returns, equity, benchmark_returns))

        # Metrics section
        sections.append(self._generate_metrics_section(result))

        # Risk section
        sections.append(self._generate_risk_section(result))

        # Statistics section
        if self.config.include_statistics:
            sections.append(self._generate_statistics_section(returns))

        # Footer
        sections.append(self._generate_footer())

        return self._wrap_html("\n".join(sections))

    def generate_comparison_report(
        self,
        results: list[dict[str, Any]],
        returns_dict: dict[str, pd.Series],
    ) -> str:
        """
        Generate strategy comparison report.

        Args:
            results: List of backtest results
            returns_dict: Dict mapping strategy names to returns

        Returns:
            HTML string
        """
        sections = []

        sections.append(self._generate_header("Strategy Comparison Report"))

        # Comparison table
        sections.append(self._generate_comparison_table(results))

        # Individual summaries
        for result in results:
            name = result.get("strategy", {}).get("name", "Unknown")
            sections.append(f"<h2>{name}</h2>")
            sections.append(self._generate_summary_section(result))

        sections.append(self._generate_footer())

        return self._wrap_html("\n".join(sections))

    def _generate_header(self, title: str | None = None) -> str:
        """Generate report header."""
        title = title or self.config.title
        return f"""
        <header class="report-header">
            <h1>{title}</h1>
            <p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p class="meta">Author: {self.config.author}</p>
        </header>
        """

    def _generate_summary_section(self, result: dict[str, Any]) -> str:
        """Generate summary section."""
        summary = result.get("summary", {})
        strategy = result.get("strategy", {})

        return f"""
        <section class="summary">
            <h2>Performance Summary</h2>
            <div class="strategy-info">
                <p><strong>Strategy:</strong> {strategy.get('name', 'Unknown')}</p>
                <p><strong>Type:</strong> {strategy.get('type', 'Unknown')}</p>
                <p><strong>Universe:</strong> {', '.join(strategy.get('universe', []))}</p>
            </div>

            <div class="metrics-grid">
                <div class="metric-card {'positive' if summary.get('total_return_pct', 0) > 0 else 'negative'}">
                    <span class="metric-value">{summary.get('total_return_pct', 0):.2f}%</span>
                    <span class="metric-label">Total Return</span>
                </div>
                <div class="metric-card">
                    <span class="metric-value">{summary.get('sharpe_ratio', 0):.2f}</span>
                    <span class="metric-label">Sharpe Ratio</span>
                </div>
                <div class="metric-card negative">
                    <span class="metric-value">{summary.get('max_drawdown_pct', 0):.2f}%</span>
                    <span class="metric-label">Max Drawdown</span>
                </div>
                <div class="metric-card">
                    <span class="metric-value">{summary.get('volatility_pct', 0):.2f}%</span>
                    <span class="metric-label">Volatility</span>
                </div>
            </div>
        </section>
        """

    def _generate_charts_section(
        self,
        returns: pd.Series,
        equity: pd.Series | None,
        benchmark_returns: pd.Series | None,
    ) -> str:
        """Generate charts section."""
        charts = []

        # Equity curve
        if equity is not None:
            benchmark_equity = None
            if benchmark_returns is not None:
                benchmark_equity = (1 + benchmark_returns).cumprod() * equity.iloc[0]
            chart = self.chart_gen.equity_curve(equity, benchmark_equity)
            if chart:
                charts.append(f'<img src="{chart}" alt="Equity Curve" />')

        # Drawdown
        chart = self.chart_gen.drawdown_chart(returns)
        if chart:
            charts.append(f'<img src="{chart}" alt="Drawdown" />')

        # Returns distribution
        chart = self.chart_gen.returns_distribution(returns)
        if chart:
            charts.append(f'<img src="{chart}" alt="Returns Distribution" />')

        # Monthly heatmap
        if len(returns) > 60:
            chart = self.chart_gen.monthly_returns_heatmap(returns)
            if chart:
                charts.append(f'<img src="{chart}" alt="Monthly Returns" />')

        # Rolling metrics
        if len(returns) > 60:
            chart = self.chart_gen.rolling_metrics(returns)
            if chart:
                charts.append(f'<img src="{chart}" alt="Rolling Metrics" />')

        if not charts:
            return ""

        return f"""
        <section class="charts">
            <h2>Performance Charts</h2>
            <div class="charts-grid">
                {''.join(f'<div class="chart">{c}</div>' for c in charts)}
            </div>
        </section>
        """

    def _generate_metrics_section(self, result: dict[str, Any]) -> str:
        """Generate detailed metrics section."""
        summary = result.get("summary", {})
        trade_stats = result.get("trade_stats", {})

        return f"""
        <section class="metrics">
            <h2>Detailed Metrics</h2>

            <div class="metrics-table">
                <h3>Return Metrics</h3>
                <table>
                    <tr><td>Total Return</td><td>{summary.get('total_return_pct', 0):.2f}%</td></tr>
                    <tr><td>Annualized Return</td><td>{summary.get('annualized_return_pct', 0):.2f}%</td></tr>
                    <tr><td>Sharpe Ratio</td><td>{summary.get('sharpe_ratio', 0):.2f}</td></tr>
                    <tr><td>Sortino Ratio</td><td>{summary.get('sortino_ratio', 0):.2f}</td></tr>
                    <tr><td>Calmar Ratio</td><td>{summary.get('calmar_ratio', 0):.2f}</td></tr>
                </table>
            </div>

            <div class="metrics-table">
                <h3>Trade Statistics</h3>
                <table>
                    <tr><td>Total Trades</td><td>{trade_stats.get('total_trades', 0)}</td></tr>
                    <tr><td>Win Rate</td><td>{trade_stats.get('win_rate_pct', 0):.1f}%</td></tr>
                    <tr><td>Profit Factor</td><td>{trade_stats.get('profit_factor', 0):.2f}</td></tr>
                    <tr><td>Avg Trade Return</td><td>{trade_stats.get('avg_trade_return_pct', 0):.2f}%</td></tr>
                    <tr><td>Avg Win</td><td>{trade_stats.get('avg_win_pct', 0):.2f}%</td></tr>
                    <tr><td>Avg Loss</td><td>{trade_stats.get('avg_loss_pct', 0):.2f}%</td></tr>
                </table>
            </div>
        </section>
        """

    def _generate_risk_section(self, result: dict[str, Any]) -> str:
        """Generate risk metrics section."""
        summary = result.get("summary", {})
        risk = result.get("risk_metrics", {})
        drawdown = result.get("drawdown_analysis", {})

        return f"""
        <section class="risk">
            <h2>Risk Analysis</h2>

            <div class="metrics-table">
                <h3>Risk Metrics</h3>
                <table>
                    <tr><td>Max Drawdown</td><td>{summary.get('max_drawdown_pct', 0):.2f}%</td></tr>
                    <tr><td>Volatility (Ann.)</td><td>{summary.get('volatility_pct', 0):.2f}%</td></tr>
                    <tr><td>VaR (95%)</td><td>{risk.get('var_95', 0):.2f}%</td></tr>
                    <tr><td>CVaR (95%)</td><td>{risk.get('cvar_95', 0):.2f}%</td></tr>
                    <tr><td>Skewness</td><td>{risk.get('skewness', 0):.3f}</td></tr>
                    <tr><td>Kurtosis</td><td>{risk.get('kurtosis', 0):.3f}</td></tr>
                </table>
            </div>

            <div class="metrics-table">
                <h3>Drawdown Analysis</h3>
                <table>
                    <tr><td>Max Drawdown</td><td>{drawdown.get('max_drawdown_pct', 0):.2f}%</td></tr>
                    <tr><td>Avg Drawdown</td><td>{drawdown.get('avg_drawdown_pct', 0):.2f}%</td></tr>
                    <tr><td>Max DD Duration</td><td>{drawdown.get('max_drawdown_duration_days', 0)} days</td></tr>
                </table>
            </div>
        </section>
        """

    def _generate_statistics_section(self, returns: pd.Series) -> str:
        """Generate statistical analysis section."""
        from .metrics.statistical import StatisticalTester

        tester = StatisticalTester()

        # Run tests
        mean_test = tester.test_mean_different_from_zero(returns.values, "greater")
        sharpe_test = tester.test_sharpe_ratio(returns.values)
        skill_test = tester.test_skill_vs_luck(returns.values, n_permutations=1000)

        return f"""
        <section class="statistics">
            <h2>Statistical Analysis</h2>

            <div class="test-result {'significant' if mean_test.significant else 'not-significant'}">
                <h4>{mean_test.test_name}</h4>
                <p>{mean_test.interpretation}</p>
                <p class="p-value">p-value: {mean_test.p_value:.4f}</p>
            </div>

            <div class="test-result {'significant' if sharpe_test.significant else 'not-significant'}">
                <h4>{sharpe_test.test_name}</h4>
                <p>{sharpe_test.interpretation}</p>
                <p class="p-value">p-value: {sharpe_test.p_value:.4f}</p>
            </div>

            <div class="test-result {'significant' if skill_test.significant else 'not-significant'}">
                <h4>{skill_test.test_name}</h4>
                <p>{skill_test.interpretation}</p>
                <p class="p-value">p-value: {skill_test.p_value:.4f}</p>
            </div>
        </section>
        """

    def _generate_comparison_table(self, results: list[dict[str, Any]]) -> str:
        """Generate strategy comparison table."""
        rows = []
        for r in results:
            strategy = r.get("strategy", {})
            summary = r.get("summary", {})
            rows.append(f"""
            <tr>
                <td>{strategy.get('name', 'Unknown')}</td>
                <td class="{'positive' if summary.get('total_return_pct', 0) > 0 else 'negative'}">{summary.get('total_return_pct', 0):.2f}%</td>
                <td>{summary.get('sharpe_ratio', 0):.2f}</td>
                <td class="negative">{summary.get('max_drawdown_pct', 0):.2f}%</td>
                <td>{summary.get('volatility_pct', 0):.2f}%</td>
                <td>{r.get('trade_stats', {}).get('win_rate_pct', 0):.1f}%</td>
            </tr>
            """)

        return f"""
        <section class="comparison">
            <h2>Strategy Comparison</h2>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Total Return</th>
                        <th>Sharpe</th>
                        <th>Max DD</th>
                        <th>Volatility</th>
                        <th>Win Rate</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(rows)}
                </tbody>
            </table>
        </section>
        """

    def _generate_footer(self) -> str:
        """Generate report footer."""
        return f"""
        <footer class="report-footer">
            <p>Generated by {self.config.author} | {datetime.now().year}</p>
            <p class="disclaimer">This report is for informational purposes only.
            Past performance does not guarantee future results.</p>
        </footer>
        """

    def _wrap_html(self, content: str) -> str:
        """Wrap content in HTML document."""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{self.config.title}</title>
    <style>
        {self._get_css()}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
        """

    def _get_css(self) -> str:
        """Get CSS styles."""
        return """
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               line-height: 1.6; color: #1f2937; background: #f9fafb; }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }

        .report-header { text-align: center; margin-bottom: 2rem; padding: 2rem;
                        background: linear-gradient(135deg, #1e40af, #3b82f6);
                        color: white; border-radius: 8px; }
        .report-header h1 { font-size: 2rem; margin-bottom: 0.5rem; }
        .report-header .meta { opacity: 0.9; font-size: 0.9rem; }

        section { background: white; padding: 1.5rem; margin-bottom: 1.5rem;
                 border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        section h2 { font-size: 1.25rem; margin-bottom: 1rem; color: #1e40af;
                    border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; }

        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                       gap: 1rem; }
        .metric-card { padding: 1.5rem; background: #f8fafc; border-radius: 8px;
                      text-align: center; border-left: 4px solid #3b82f6; }
        .metric-card.positive { border-left-color: #22c55e; }
        .metric-card.negative { border-left-color: #ef4444; }
        .metric-value { display: block; font-size: 2rem; font-weight: bold; color: #1f2937; }
        .metric-label { font-size: 0.875rem; color: #6b7280; }

        .metrics-table { margin-bottom: 1.5rem; }
        .metrics-table h3 { font-size: 1rem; margin-bottom: 0.75rem; color: #374151; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e7eb; }
        th { background: #f8fafc; font-weight: 600; }
        td.positive { color: #22c55e; }
        td.negative { color: #ef4444; }

        .comparison-table { width: 100%; }
        .comparison-table th { background: #1e40af; color: white; }

        .charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                      gap: 1.5rem; }
        .chart img { max-width: 100%; height: auto; border-radius: 4px; }

        .test-result { padding: 1rem; margin-bottom: 1rem; border-radius: 8px;
                      border-left: 4px solid #6b7280; background: #f8fafc; }
        .test-result.significant { border-left-color: #22c55e; }
        .test-result.not-significant { border-left-color: #f59e0b; }
        .test-result h4 { margin-bottom: 0.5rem; }
        .p-value { font-size: 0.875rem; color: #6b7280; margin-top: 0.5rem; }

        .report-footer { text-align: center; padding: 1.5rem; color: #6b7280;
                        font-size: 0.875rem; }
        .disclaimer { margin-top: 0.5rem; font-style: italic; }

        @media print {
            body { background: white; }
            .container { padding: 0; }
            section { box-shadow: none; page-break-inside: avoid; }
        }
        """


# =============================================================================
# DAILY REPORT GENERATOR
# =============================================================================

@dataclass
class DailyReportData:
    """Data for daily trading report."""

    date: str
    signals: list[dict]
    executions: list[dict]
    portfolio_value: float
    daily_pnl: float
    positions: list[dict]
    backtest_expectations: dict | None = None


class DailyReportGenerator:
    """
    Generate enhanced daily trading reports.

    Features:
    - Backtest vs live comparison
    - Strategy-level attribution
    - Signal hit rate tracking
    - Slippage analysis
    """

    def __init__(self, output_dir: Path | str | None = None):
        """Initialize daily report generator."""
        self.output_dir = Path(output_dir or Path.home() / "quant_results" / "daily_reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_daily_report(
        self,
        data: DailyReportData,
        historical_signals: list[dict] | None = None,
    ) -> dict:
        """
        Generate comprehensive daily report.

        Args:
            data: Daily report data
            historical_signals: Past signals for hit rate calculation

        Returns:
            Report dictionary
        """
        report = {
            "report_date": data.date,
            "generated_at": datetime.now().isoformat(),
            "summary": self._generate_summary(data),
            "strategy_attribution": self._generate_attribution(data),
            "signal_analysis": self._generate_signal_analysis(data, historical_signals),
            "execution_analysis": self._generate_execution_analysis(data),
            "backtest_comparison": self._generate_backtest_comparison(data),
            "positions": data.positions,
        }

        # Save report
        self._save_report(report, data.date)

        return report

    def _generate_summary(self, data: DailyReportData) -> dict:
        """Generate daily summary."""
        successful_execs = [e for e in data.executions if e.get("success", False)]
        failed_execs = [e for e in data.executions if not e.get("success", False)]

        return {
            "date": data.date,
            "portfolio_value": data.portfolio_value,
            "daily_pnl": data.daily_pnl,
            "daily_return_pct": (data.daily_pnl / (data.portfolio_value - data.daily_pnl) * 100)
                               if data.portfolio_value > data.daily_pnl else 0,
            "signals_generated": len(data.signals),
            "buy_signals": sum(1 for s in data.signals if s.get("direction") == "LONG"),
            "sell_signals": sum(1 for s in data.signals if s.get("direction") == "SHORT"),
            "executions_attempted": len(data.executions),
            "executions_successful": len(successful_execs),
            "executions_failed": len(failed_execs),
            "positions_count": len(data.positions),
        }

    def _generate_attribution(self, data: DailyReportData) -> dict:
        """Generate strategy-level attribution."""
        by_strategy = {}

        # Group signals by strategy
        for signal in data.signals:
            strategy = signal.get("strategy", "unknown")
            if strategy not in by_strategy:
                by_strategy[strategy] = {
                    "signals": 0,
                    "buy": 0,
                    "sell": 0,
                    "avg_strength": 0,
                    "avg_confidence": 0,
                    "executions": 0,
                    "pnl_contribution": 0,
                }

            by_strategy[strategy]["signals"] += 1
            by_strategy[strategy]["avg_strength"] += signal.get("strength", 0)
            by_strategy[strategy]["avg_confidence"] += signal.get("confidence", 0)

            if signal.get("direction") == "LONG":
                by_strategy[strategy]["buy"] += 1
            else:
                by_strategy[strategy]["sell"] += 1

        # Calculate averages and add execution info
        for strategy, stats in by_strategy.items():
            if stats["signals"] > 0:
                stats["avg_strength"] /= stats["signals"]
                stats["avg_confidence"] /= stats["signals"]

            # Count executions for this strategy
            for exec_data in data.executions:
                if exec_data.get("strategy") == strategy and exec_data.get("success"):
                    stats["executions"] += 1

        return by_strategy

    def _generate_signal_analysis(
        self,
        data: DailyReportData,
        historical_signals: list[dict] | None = None,
    ) -> dict:
        """Generate signal analysis including hit rate."""
        analysis = {
            "total_signals": len(data.signals),
            "by_symbol": {},
            "strength_distribution": {
                "strong": 0,  # >= 0.7
                "medium": 0,  # 0.5 - 0.7
                "weak": 0,    # < 0.5
            },
            "hit_rate": None,
        }

        # Analyze signals by symbol
        for signal in data.signals:
            symbol = signal.get("symbol", "unknown")
            if symbol not in analysis["by_symbol"]:
                analysis["by_symbol"][symbol] = {"count": 0, "directions": []}
            analysis["by_symbol"][symbol]["count"] += 1
            analysis["by_symbol"][symbol]["directions"].append(signal.get("direction"))

            # Strength distribution
            strength = signal.get("strength", 0)
            if strength >= 0.7:
                analysis["strength_distribution"]["strong"] += 1
            elif strength >= 0.5:
                analysis["strength_distribution"]["medium"] += 1
            else:
                analysis["strength_distribution"]["weak"] += 1

        # Calculate hit rate from historical signals
        if historical_signals:
            hit_rate = self._calculate_hit_rate(historical_signals)
            analysis["hit_rate"] = hit_rate

        return analysis

    def _calculate_hit_rate(self, historical_signals: list[dict]) -> dict:
        """Calculate signal hit rate from historical data."""
        total = len(historical_signals)
        if total == 0:
            return {"total": 0, "profitable": 0, "hit_rate": 0}

        profitable = sum(1 for s in historical_signals if s.get("was_profitable", False))

        return {
            "total": total,
            "profitable": profitable,
            "hit_rate": profitable / total * 100 if total > 0 else 0,
            "by_strategy": self._hit_rate_by_strategy(historical_signals),
        }

    def _hit_rate_by_strategy(self, signals: list[dict]) -> dict:
        """Calculate hit rate by strategy."""
        by_strategy = {}
        for signal in signals:
            strategy = signal.get("strategy", "unknown")
            if strategy not in by_strategy:
                by_strategy[strategy] = {"total": 0, "profitable": 0}
            by_strategy[strategy]["total"] += 1
            if signal.get("was_profitable", False):
                by_strategy[strategy]["profitable"] += 1

        # Calculate rates
        for strategy, stats in by_strategy.items():
            stats["hit_rate"] = stats["profitable"] / stats["total"] * 100 if stats["total"] > 0 else 0

        return by_strategy

    def _generate_execution_analysis(self, data: DailyReportData) -> dict:
        """Generate execution and slippage analysis."""
        executions = data.executions
        if not executions:
            return {"total": 0, "slippage_analysis": None}

        successful = [e for e in executions if e.get("success")]
        slippages = [e.get("slippage_bps", 0) for e in successful if e.get("slippage_bps") is not None]

        analysis = {
            "total": len(executions),
            "successful": len(successful),
            "failed": len(executions) - len(successful),
            "success_rate": len(successful) / len(executions) * 100 if executions else 0,
        }

        if slippages:
            import statistics
            analysis["slippage_analysis"] = {
                "avg_slippage_bps": statistics.mean(slippages),
                "max_slippage_bps": max(slippages),
                "min_slippage_bps": min(slippages),
                "std_slippage_bps": statistics.stdev(slippages) if len(slippages) > 1 else 0,
                "positive_slippage_count": sum(1 for s in slippages if s > 0),
                "negative_slippage_count": sum(1 for s in slippages if s < 0),
            }
        else:
            analysis["slippage_analysis"] = None

        return analysis

    def _generate_backtest_comparison(self, data: DailyReportData) -> dict | None:
        """Compare live results to backtest expectations."""
        if not data.backtest_expectations:
            return None

        expected = data.backtest_expectations
        actual_signals = len(data.signals)
        expected_signals = expected.get("avg_daily_signals", 0)

        return {
            "signal_deviation": {
                "expected": expected_signals,
                "actual": actual_signals,
                "deviation_pct": (actual_signals - expected_signals) / expected_signals * 100
                                if expected_signals > 0 else 0,
            },
            "return_deviation": {
                "expected_daily_return": expected.get("avg_daily_return", 0),
                "actual_daily_return": data.daily_pnl / (data.portfolio_value - data.daily_pnl) * 100
                                      if data.portfolio_value > data.daily_pnl else 0,
            },
            "execution_quality": {
                "expected_fill_rate": expected.get("expected_fill_rate", 100),
                "actual_fill_rate": len([e for e in data.executions if e.get("success")]) /
                                   len(data.executions) * 100 if data.executions else 100,
            },
            "notes": self._generate_comparison_notes(data, expected),
        }

    def _generate_comparison_notes(self, data: DailyReportData, expected: dict) -> list[str]:
        """Generate notes on backtest vs live comparison."""
        notes = []

        # Signal count deviation
        actual_signals = len(data.signals)
        expected_signals = expected.get("avg_daily_signals", 0)
        if expected_signals > 0:
            deviation = abs(actual_signals - expected_signals) / expected_signals * 100
            if deviation > 50:
                notes.append(f"Signal count significantly differs from backtest ({deviation:.0f}% deviation)")

        # Execution issues
        if data.executions:
            failed = len([e for e in data.executions if not e.get("success")])
            if failed > 0:
                notes.append(f"{failed} execution(s) failed - review broker connection")

        # Slippage warning
        slippages = [e.get("slippage_bps", 0) for e in data.executions if e.get("slippage_bps")]
        if slippages and max(slippages) > 50:
            notes.append(f"High slippage detected ({max(slippages):.0f}bps) - consider limit orders")

        if not notes:
            notes.append("Performance tracking in line with backtest expectations")

        return notes

    def _save_report(self, report: dict, date: str) -> None:
        """Save report to file."""
        filename = f"daily_report_{date.replace('-', '')}.json"
        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Daily report saved to: {filepath}")

    def generate_html_daily_report(self, data: DailyReportData) -> str:
        """Generate HTML daily report."""
        report = self.generate_daily_report(data)

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Daily Trading Report - {data.date}</title>
    <style>
        body {{ font-family: sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #1e40af; color: white; padding: 20px; border-radius: 8px; }}
        .section {{ background: #f8fafc; padding: 15px; margin: 15px 0; border-radius: 8px; }}
        .metric {{ display: inline-block; margin: 10px; padding: 10px; background: white; border-radius: 4px; }}
        .positive {{ color: #22c55e; }}
        .negative {{ color: #ef4444; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Daily Trading Report</h1>
        <p>{data.date}</p>
    </div>

    <div class="section">
        <h2>Summary</h2>
        <div class="metric">
            <strong>Portfolio Value:</strong> ${report['summary']['portfolio_value']:,.2f}
        </div>
        <div class="metric {'positive' if report['summary']['daily_pnl'] >= 0 else 'negative'}">
            <strong>Daily P&L:</strong> ${report['summary']['daily_pnl']:,.2f}
            ({report['summary']['daily_return_pct']:.2f}%)
        </div>
        <div class="metric">
            <strong>Signals:</strong> {report['summary']['signals_generated']}
            ({report['summary']['buy_signals']} buy / {report['summary']['sell_signals']} sell)
        </div>
        <div class="metric">
            <strong>Executions:</strong> {report['summary']['executions_successful']}/{report['summary']['executions_attempted']}
        </div>
    </div>

    <div class="section">
        <h2>Strategy Attribution</h2>
        <table>
            <tr>
                <th>Strategy</th>
                <th>Signals</th>
                <th>Buy/Sell</th>
                <th>Avg Strength</th>
                <th>Executions</th>
            </tr>
            {''.join(f"<tr><td>{s}</td><td>{d['signals']}</td><td>{d['buy']}/{d['sell']}</td><td>{d['avg_strength']:.2f}</td><td>{d['executions']}</td></tr>" for s, d in report['strategy_attribution'].items())}
        </table>
    </div>

    <div class="section">
        <h2>Execution Analysis</h2>
        <p>Success Rate: {report['execution_analysis']['success_rate']:.1f}%</p>
        {self._format_slippage_html(report['execution_analysis'].get('slippage_analysis'))}
    </div>

    {self._format_backtest_comparison_html(report.get('backtest_comparison'))}

    <footer style="text-align: center; margin-top: 30px; color: #666;">
        Generated at {report['generated_at']}
    </footer>
</body>
</html>
        """

        return html

    def _format_slippage_html(self, slippage: dict | None) -> str:
        """Format slippage analysis as HTML."""
        if not slippage:
            return "<p>No slippage data available</p>"

        return f"""
        <p>Average Slippage: {slippage['avg_slippage_bps']:.1f}bps</p>
        <p>Max Slippage: {slippage['max_slippage_bps']:.1f}bps</p>
        """

    def _format_backtest_comparison_html(self, comparison: dict | None) -> str:
        """Format backtest comparison as HTML."""
        if not comparison:
            return ""

        notes_html = "".join(f"<li>{note}</li>" for note in comparison.get("notes", []))

        return f"""
        <div class="section">
            <h2>Backtest vs Live Comparison</h2>
            <p>Signal Deviation: {comparison['signal_deviation']['deviation_pct']:.1f}%</p>
            <p>Fill Rate: {comparison['execution_quality']['actual_fill_rate']:.1f}% (expected: {comparison['execution_quality']['expected_fill_rate']:.1f}%)</p>
            <h4>Notes:</h4>
            <ul>{notes_html}</ul>
        </div>
        """


# Convenience functions
def generate_backtest_report(
    result: dict[str, Any],
    returns: pd.Series,
    equity: pd.Series | None = None,
    output_path: str | Path | None = None,
) -> str:
    """
    Generate HTML backtest report.

    Args:
        result: Backtest result dictionary
        returns: Strategy returns
        equity: Equity curve
        output_path: Optional path to save report

    Returns:
        HTML string
    """
    generator = HTMLReportGenerator()
    html = generator.generate_backtest_report(result, returns, equity)

    if output_path:
        Path(output_path).write_text(html)
        logger.info(f"Report saved to {output_path}")

    return html


def generate_comparison_report(
    results: list[dict[str, Any]],
    returns_dict: dict[str, pd.Series],
    output_path: str | Path | None = None,
) -> str:
    """
    Generate strategy comparison report.

    Args:
        results: List of backtest results
        returns_dict: Strategy returns
        output_path: Optional path to save report

    Returns:
        HTML string
    """
    generator = HTMLReportGenerator(ReportConfig(title="Strategy Comparison Report"))
    html = generator.generate_comparison_report(results, returns_dict)

    if output_path:
        Path(output_path).write_text(html)
        logger.info(f"Report saved to {output_path}")

    return html


def generate_json_report(
    result: dict[str, Any],
    output_path: str | Path | None = None,
) -> str:
    """
    Generate JSON report for programmatic access.

    Args:
        result: Backtest result
        output_path: Optional path to save

    Returns:
        JSON string
    """
    report = {
        "generated_at": datetime.now().isoformat(),
        "report_type": "backtest",
        "data": result,
    }

    json_str = json.dumps(report, indent=2, default=str)

    if output_path:
        Path(output_path).write_text(json_str)

    return json_str
