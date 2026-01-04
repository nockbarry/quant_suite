"""
Main analysis runner for Claude Code.

Provides high-level entry points for common analysis workflows with
automatic session management and artifact persistence.

All results are saved to ~/quant_results/ for easy viewing.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
import json
import base64

import numpy as np
import pandas as pd

from .session import Session, SessionManager, SessionResult
from ..screeners.composite_screener import CompositeScreener

# Optional matplotlib import
HAS_MATPLOTLIB = False
MCPTVisualizer = None
try:
    from ..visualizations.mcpt_charts import MCPTVisualizer, HAS_MATPLOTLIB as _HAS_MPL
    HAS_MATPLOTLIB = _HAS_MPL
except ImportError:
    pass


@dataclass
class AnalysisResult:
    """Structured result from any analysis."""

    success: bool
    session: Session | None
    session_result: SessionResult | None
    metrics: dict[str, Any]
    interpretation: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "session_id": self.session.session_id if self.session else None,
            "session_path": str(self.session.session_path) if self.session else None,
            "metrics": self.metrics,
            "interpretation": self.interpretation,
            "error": self.error,
        }


class AnalysisRunner:
    """
    High-level analysis runner for Claude Code.

    Provides simple entry points for:
    - MCPT analysis with visualizations
    - Stock screening with alt data
    - Full strategy development workflows

    All outputs are automatically persisted to ~/quant_results/.

    Usage:
        runner = AnalysisRunner()
        result = await runner.run_mcpt_analysis(strategy, data)
        print(f"Report at: {result.session.session_path}/report.html")
    """

    def __init__(self):
        self.viz = None
        if HAS_MATPLOTLIB and MCPTVisualizer is not None:
            try:
                self.viz = MCPTVisualizer()
            except ImportError:
                pass  # matplotlib not fully available

    async def run_mcpt_analysis(
        self,
        strategy_name: str,
        strategy_returns: pd.Series,
        permutation_returns: list[pd.Series],
        symbols: list[str],
        session_name: str | None = None,
        metrics_to_test: list[str] | None = None,
    ) -> AnalysisResult:
        """
        Run MCPT analysis with full visualization and persistence.

        Args:
            strategy_name: Name of the strategy being tested
            strategy_returns: Returns from the actual strategy
            permutation_returns: List of returns from permuted data
            symbols: Symbols analyzed
            session_name: Optional custom session name
            metrics_to_test: Metrics to compute (default: sharpe, return, sortino)

        Returns:
            AnalysisResult with session containing all artifacts

        Example:
            result = await runner.run_mcpt_analysis(
                strategy_name="SMA_10_30",
                strategy_returns=backtest_result.returns,
                permutation_returns=[perm.returns for perm in permuted_results],
                symbols=["AAPL", "NVDA"]
            )
            print(f"P-value: {result.metrics['sharpe_p_value']:.4f}")
        """
        session_name = session_name or f"mcpt_{strategy_name}"
        metrics_to_test = metrics_to_test or ["sharpe_ratio", "total_return", "sortino_ratio"]

        session = SessionManager.create(
            name=session_name,
            session_type="mcpt",
            symbols=symbols,
            description=f"MCPT analysis of {strategy_name}",
        )

        try:
            # Calculate metrics for original strategy
            original_metrics = self._calculate_metrics(strategy_returns)

            # Calculate metrics for all permutations
            permutation_metrics: dict[str, list[float]] = {m: [] for m in metrics_to_test}
            for perm_returns in permutation_returns:
                perm_m = self._calculate_metrics(perm_returns)
                for metric in metrics_to_test:
                    if metric in perm_m:
                        permutation_metrics[metric].append(perm_m[metric])

            # Calculate p-values
            p_values = {}
            is_significant = {}
            percentiles = {}

            for metric in metrics_to_test:
                if metric not in permutation_metrics or len(permutation_metrics[metric]) == 0:
                    continue

                perm_values = np.array(permutation_metrics[metric])
                orig_value = original_metrics.get(metric, 0)

                # P-value: proportion of permutations >= original
                p_value = np.mean(perm_values >= orig_value)
                p_values[metric] = p_value
                is_significant[metric] = p_value < 0.05

                percentiles[metric] = {
                    "5%": float(np.percentile(perm_values, 5)),
                    "25%": float(np.percentile(perm_values, 25)),
                    "50%": float(np.percentile(perm_values, 50)),
                    "75%": float(np.percentile(perm_values, 75)),
                    "95%": float(np.percentile(perm_values, 95)),
                }

            # Generate visualizations (if matplotlib available)
            charts_saved = []
            if self.viz is not None:
                for metric in metrics_to_test:
                    if metric in permutation_metrics and len(permutation_metrics[metric]) > 0:
                        fig = self.viz.plot_permutation_distribution(
                            permutation_values=permutation_metrics[metric],
                            original_value=original_metrics.get(metric, 0),
                            p_value=p_values.get(metric, 1.0),
                            metric_name=metric.replace("_", " ").title(),
                            strategy_name=strategy_name,
                        )
                        chart_path = session.save_chart(fig, f"mcpt_{metric}")
                        charts_saved.append(chart_path)
                        import matplotlib.pyplot as plt
                        plt.close(fig)

            # Generate HTML report
            html_report = self._generate_mcpt_html_report(
                strategy_name=strategy_name,
                original_metrics=original_metrics,
                p_values=p_values,
                is_significant=is_significant,
                percentiles=percentiles,
                n_permutations=len(permutation_returns),
                charts=charts_saved,
            )
            session.save_html_report(html_report)

            # Save raw data
            results_data = {
                "strategy_name": strategy_name,
                "n_permutations": len(permutation_returns),
                "original_metrics": original_metrics,
                "p_values": p_values,
                "is_significant": is_significant,
                "percentiles": percentiles,
            }
            session.save_data(results_data, "mcpt_results", format="json")

            # Save metrics CSV
            metrics_df = pd.DataFrame([{
                "metric": m,
                "original_value": original_metrics.get(m, 0),
                "p_value": p_values.get(m, 1.0),
                "is_significant": is_significant.get(m, False),
                "perm_5th": percentiles.get(m, {}).get("5%", 0),
                "perm_95th": percentiles.get(m, {}).get("95%", 0),
            } for m in metrics_to_test])
            session.save_data(metrics_df, "mcpt_metrics", format="csv")

            # Generate interpretation
            interpretation = self._interpret_mcpt_results(
                strategy_name=strategy_name,
                original_metrics=original_metrics,
                p_values=p_values,
                is_significant=is_significant,
                n_permutations=len(permutation_returns),
            )

            # Complete session
            summary_metrics = {
                "strategy_name": strategy_name,
                "n_permutations": len(permutation_returns),
                "sharpe_ratio": original_metrics.get("sharpe_ratio"),
                "sharpe_p_value": p_values.get("sharpe_ratio"),
                "sharpe_significant": is_significant.get("sharpe_ratio"),
                "total_return": original_metrics.get("total_return"),
                "return_p_value": p_values.get("total_return"),
            }
            session_result = session.complete(summary_metrics, interpretation)

            return AnalysisResult(
                success=True,
                session=session,
                session_result=session_result,
                metrics=summary_metrics,
                interpretation=interpretation,
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                session=session,
                session_result=None,
                metrics={},
                interpretation="",
                error=str(e),
            )

    async def run_stock_screen(
        self,
        symbols: list[str],
        price_data: dict[str, pd.DataFrame] | None = None,
        min_signals: int = 2,
        session_name: str | None = None,
    ) -> AnalysisResult:
        """
        Run stock screening with alternative data.

        Args:
            symbols: Symbols to screen
            price_data: Optional pre-loaded OHLCV data
            min_signals: Minimum signals required
            session_name: Optional custom session name

        Returns:
            AnalysisResult with screened stocks
        """
        session_name = session_name or f"screen_{len(symbols)}_stocks"
        session = SessionManager.create(
            name=session_name,
            session_type="screen",
            symbols=symbols,
        )

        try:
            screener = CompositeScreener()
            results = await screener.screen(
                symbols,
                min_signals=min_signals,
                price_data=price_data,
            )

            # Convert to list of dicts
            results_dicts = [r.to_dict() for r in results]

            # Save data
            session.save_data(results_dicts, "screener_results", format="json")

            # Create CSV of ranked picks
            picks_df = pd.DataFrame([{
                "rank": i + 1,
                "symbol": r.symbol,
                "signal": r.overall_signal,
                "score": r.overall_score,
                "n_bullish": sum(1 for s in r.signals if s.signal == "bullish"),
                "n_bearish": sum(1 for s in r.signals if s.signal == "bearish"),
            } for i, r in enumerate(results)])
            session.save_data(picks_df, "ranked_picks", format="csv")

            # Generate HTML report
            html_report = self._generate_screen_html_report(
                results=results,
                symbols=symbols,
            )
            session.save_html_report(html_report)

            # Interpretation
            interpretation = self._interpret_screen_results(results)

            metrics = {
                "stocks_screened": len(symbols),
                "stocks_passing": len(results),
                "top_pick": results[0].symbol if results else None,
                "top_score": results[0].overall_score if results else None,
            }
            session_result = session.complete(metrics, interpretation)

            return AnalysisResult(
                success=True,
                session=session,
                session_result=session_result,
                metrics=metrics,
                interpretation=interpretation,
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                session=session,
                session_result=None,
                metrics={},
                interpretation="",
                error=str(e),
            )

    def _calculate_metrics(self, returns: pd.Series) -> dict[str, float]:
        """Calculate standard performance metrics from returns."""
        clean_returns = returns.dropna()
        if len(clean_returns) < 10:
            return {}

        total_return = (1 + clean_returns).prod() - 1
        mean_return = clean_returns.mean()
        std_return = clean_returns.std()

        # Sharpe ratio (annualized)
        sharpe = (mean_return / std_return) * np.sqrt(252) if std_return > 0 else 0

        # Sortino ratio
        downside_returns = clean_returns[clean_returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else std_return
        sortino = (mean_return / downside_std) * np.sqrt(252) if downside_std > 0 else 0

        # Max drawdown
        cum_returns = (1 + clean_returns).cumprod()
        rolling_max = cum_returns.expanding().max()
        drawdown = (cum_returns - rolling_max) / rolling_max
        max_drawdown = drawdown.min()

        # Win rate
        wins = (clean_returns > 0).sum()
        total = len(clean_returns)
        win_rate = wins / total if total > 0 else 0

        return {
            "total_return": float(total_return),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "max_drawdown": float(max_drawdown),
            "win_rate": float(win_rate),
            "volatility": float(std_return * np.sqrt(252)),
        }

    def _generate_mcpt_html_report(
        self,
        strategy_name: str,
        original_metrics: dict,
        p_values: dict,
        is_significant: dict,
        percentiles: dict,
        n_permutations: int,
        charts: list[Path],
    ) -> str:
        """Generate HTML report for MCPT results."""

        # Build metrics table rows
        metrics_rows = ""
        for metric, value in original_metrics.items():
            p_val = p_values.get(metric, "N/A")
            sig = is_significant.get(metric, False)
            sig_class = "significant" if sig else "not-significant"
            sig_text = "Yes" if sig else "No"

            if isinstance(p_val, float):
                p_val_str = f"{p_val:.4f}"
            else:
                p_val_str = str(p_val)

            metrics_rows += f"""
            <tr class="{sig_class}">
                <td>{metric.replace('_', ' ').title()}</td>
                <td>{value:.4f}</td>
                <td>{p_val_str}</td>
                <td>{sig_text}</td>
            </tr>
            """

        # Embed charts as base64
        charts_html = ""
        for chart_path in charts:
            if chart_path.exists():
                with open(chart_path, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
                metric_name = chart_path.stem.replace("mcpt_", "").replace("_", " ").title()
                charts_html += f"""
                <div class="chart">
                    <h3>{metric_name}</h3>
                    <img src="data:image/png;base64,{img_data}" alt="{metric_name}" />
                </div>
                """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>MCPT Analysis: {strategy_name}</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            background: #f9fafb;
            color: #1f2937;
        }}
        h1 {{ color: #1e40af; margin-bottom: 0.5rem; }}
        h2 {{ color: #374151; margin-top: 2rem; border-bottom: 2px solid #e5e7eb; padding-bottom: 0.5rem; }}
        .meta {{ color: #6b7280; margin-bottom: 2rem; }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 1rem 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{
            border: 1px solid #e5e7eb;
            padding: 0.75rem 1rem;
            text-align: left;
        }}
        th {{ background: #f3f4f6; font-weight: 600; }}
        tr.significant {{ background: #dcfce7; }}
        tr.not-significant {{ background: #fef9c3; }}
        .chart {{
            margin: 1.5rem 0;
            background: white;
            padding: 1rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .chart img {{ max-width: 100%; height: auto; }}
        .summary-box {{
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            margin: 1rem 0;
        }}
        .stat {{ display: inline-block; margin-right: 2rem; }}
        .stat-value {{ font-size: 1.5rem; font-weight: bold; color: #1e40af; }}
        .stat-label {{ font-size: 0.875rem; color: #6b7280; }}
    </style>
</head>
<body>
    <h1>MCPT Analysis: {strategy_name}</h1>
    <p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Permutations: {n_permutations}</p>

    <div class="summary-box">
        <div class="stat">
            <div class="stat-value">{original_metrics.get('sharpe_ratio', 0):.2f}</div>
            <div class="stat-label">Sharpe Ratio</div>
        </div>
        <div class="stat">
            <div class="stat-value">{original_metrics.get('total_return', 0):.1%}</div>
            <div class="stat-label">Total Return</div>
        </div>
        <div class="stat">
            <div class="stat-value">{p_values.get('sharpe_ratio', 1.0):.4f}</div>
            <div class="stat-label">Sharpe P-Value</div>
        </div>
    </div>

    <h2>Results Summary</h2>
    <table>
        <thead>
            <tr>
                <th>Metric</th>
                <th>Original Value</th>
                <th>P-Value</th>
                <th>Significant</th>
            </tr>
        </thead>
        <tbody>
            {metrics_rows}
        </tbody>
    </table>

    <h2>Distribution Charts</h2>
    {charts_html}

    <h2>Interpretation</h2>
    <div class="summary-box">
        <p>See <code>interpretation.md</code> for detailed analysis.</p>
    </div>
</body>
</html>
        """
        return html

    def _generate_screen_html_report(
        self,
        results: list,
        symbols: list[str],
    ) -> str:
        """Generate HTML report for screening results."""

        # Build results table
        results_rows = ""
        for i, r in enumerate(results[:20], 1):
            signal_class = "buy" if r.overall_signal in ["buy", "strong_buy"] else \
                          "sell" if r.overall_signal in ["sell", "strong_sell"] else "neutral"
            results_rows += f"""
            <tr class="{signal_class}">
                <td>{i}</td>
                <td><strong>{r.symbol}</strong></td>
                <td>{r.overall_signal.replace('_', ' ').title()}</td>
                <td>{r.overall_score:.3f}</td>
                <td>{sum(1 for s in r.signals if s.signal == 'bullish')}</td>
                <td>{sum(1 for s in r.signals if s.signal == 'bearish')}</td>
            </tr>
            """

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Stock Screener Results</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
            background: #f9fafb;
        }}
        h1 {{ color: #1e40af; }}
        table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; }}
        th, td {{ border: 1px solid #e5e7eb; padding: 0.75rem; text-align: left; }}
        th {{ background: #f3f4f6; }}
        tr.buy {{ background: #dcfce7; }}
        tr.sell {{ background: #fee2e2; }}
        .meta {{ color: #6b7280; }}
    </style>
</head>
<body>
    <h1>Stock Screener Results</h1>
    <p class="meta">Screened: {len(symbols)} stocks | Passing: {len(results)} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

    <table>
        <thead>
            <tr>
                <th>Rank</th>
                <th>Symbol</th>
                <th>Signal</th>
                <th>Score</th>
                <th>Bullish</th>
                <th>Bearish</th>
            </tr>
        </thead>
        <tbody>
            {results_rows}
        </tbody>
    </table>
</body>
</html>
        """
        return html

    def _interpret_mcpt_results(
        self,
        strategy_name: str,
        original_metrics: dict,
        p_values: dict,
        is_significant: dict,
        n_permutations: int,
    ) -> str:
        """Generate natural language interpretation of MCPT results."""
        interpretation = f"""# MCPT Analysis Interpretation

## Strategy: {strategy_name}
## Permutations: {n_permutations}

### Key Findings

"""
        for metric, is_sig in is_significant.items():
            p_val = p_values.get(metric, 1.0)
            orig = original_metrics.get(metric, 0)

            if is_sig:
                interpretation += f"""**{metric.replace('_', ' ').title()}**: SIGNIFICANT (p={p_val:.4f})
- Original value: {orig:.4f}
- The strategy's {metric.replace('_', ' ')} is unlikely to be due to chance alone.

"""
            else:
                interpretation += f"""**{metric.replace('_', ' ').title()}**: Not significant (p={p_val:.4f})
- Original value: {orig:.4f}
- This result could plausibly have occurred by random chance.

"""

        # Add recommendation
        n_significant = sum(is_significant.values())
        total_metrics = len(is_significant)

        if n_significant == total_metrics and total_metrics > 0:
            interpretation += """
### Recommendation

**PROMISING**: All tested metrics show statistical significance. This strategy appears to capture
genuine market patterns rather than random noise. Consider:
- Forward testing with walk-forward validation
- Paper trading to verify live performance
- Position sizing based on confidence level
"""
        elif n_significant > 0:
            interpretation += """
### Recommendation

**MIXED**: Some metrics are significant while others are not. This suggests the strategy may have
merit but requires careful consideration:
- Investigate which aspects are robust vs. potentially overfit
- Consider ensemble approaches or parameter ranges
- Use conservative position sizing
"""
        else:
            interpretation += """
### Recommendation

**CAUTION**: No metrics showed statistical significance. The observed performance is likely due to
overfitting or random chance. Actions:
- Do not deploy this strategy in production
- Review strategy logic for potential flaws
- Consider alternative approaches
"""

        return interpretation

    def _interpret_screen_results(self, results: list) -> str:
        """Generate interpretation for screening results."""
        if not results:
            return "No stocks passed the screening criteria."

        interpretation = f"""# Stock Screening Interpretation

## Summary
- **Stocks Passing**: {len(results)}
- **Top Pick**: {results[0].symbol} ({results[0].overall_signal})

## Top 5 Picks

"""
        for i, r in enumerate(results[:5], 1):
            bullish = sum(1 for s in r.signals if s.signal == "bullish")
            bearish = sum(1 for s in r.signals if s.signal == "bearish")

            interpretation += f"""### {i}. {r.symbol}
- **Signal**: {r.overall_signal.replace('_', ' ').title()}
- **Score**: {r.overall_score:.3f}
- **Bullish Signals**: {bullish}
- **Bearish Signals**: {bearish}

"""

        return interpretation


# Convenience functions for Claude Code

async def analyze_strategy_mcpt(
    strategy_name: str,
    strategy_returns: pd.Series,
    permutation_returns: list[pd.Series],
    symbols: list[str],
    **kwargs,
) -> AnalysisResult:
    """
    Quick MCPT analysis - main entry point for Claude Code.

    Example:
        result = await analyze_strategy_mcpt(
            strategy_name="SMA_10_30",
            strategy_returns=backtest.returns,
            permutation_returns=[p.returns for p in permuted],
            symbols=["AAPL", "NVDA"]
        )
        print(f"Session at: {result.session.session_path}")
    """
    runner = AnalysisRunner()
    return await runner.run_mcpt_analysis(
        strategy_name=strategy_name,
        strategy_returns=strategy_returns,
        permutation_returns=permutation_returns,
        symbols=symbols,
        **kwargs,
    )


async def screen_stocks(
    symbols: list[str],
    price_data: dict[str, pd.DataFrame] | None = None,
    min_signals: int = 2,
    **kwargs,
) -> AnalysisResult:
    """
    Stock screening with alt data - entry point for Claude Code.
    """
    runner = AnalysisRunner()
    return await runner.run_stock_screen(
        symbols=symbols,
        price_data=price_data,
        min_signals=min_signals,
        **kwargs,
    )
