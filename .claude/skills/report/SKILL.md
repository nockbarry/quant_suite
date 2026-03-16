---
name: report
description: Generate comprehensive reports with tables, figures, and next steps for strategies, research cycles, and trading performance. Use when documenting results, creating summaries, generating visualizations, or preparing strategy documentation.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, Edit
---

# Report Generation Skill

Generate comprehensive documentation for strategies, research, and trading.

## Report Types

| Report | Purpose | Output |
|--------|---------|--------|
| Strategy Report | Full strategy documentation | Markdown + figures |
| Research Cycle | Research session summary | JSON + Markdown |
| Performance Report | Trading performance | Tables + charts |
| Validation Report | Pre-promotion checklist | Structured JSON |
| Weekly Summary | Portfolio review | Dashboard |

## Quick Start

```bash
# Generate strategy report
PYTHONPATH=. python scripts/generate_report.py --type strategy --name bollinger_reversal --symbol QCOM

# Generate research summary
PYTHONPATH=. python scripts/generate_report.py --type research --cycle cycle_20260103_195257

# Generate performance report
PYTHONPATH=. python scripts/generate_report.py --type performance --days 30
```

## Strategy Report Template

```python
from datetime import datetime
from pathlib import Path
import json

def generate_strategy_report(strategy_name, symbol, results):
    """
    Generate comprehensive strategy documentation.
    """
    report = f"""# Strategy Report: {strategy_name} on {symbol}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Status**: {'PRODUCTION' if results.get('in_production') else 'RESEARCH'}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Validation Sharpe | {results.get('val_sharpe', 'N/A'):.2f} |
| MCPT p-value | {results.get('p_value', 'N/A'):.4f} |
| Win Rate | {results.get('win_rate', 'N/A'):.1%} |
| Max Drawdown | {results.get('max_drawdown', 'N/A'):.1%} |
| Trades/Year | {results.get('trades_per_year', 'N/A'):.0f} |

---

## Strategy Description

**Type**: {results.get('strategy_type', 'Unknown')}
**Universe**: {symbol}
**Holding Period**: {results.get('holding_period', 'Variable')}

### Entry Conditions
{results.get('entry_conditions', 'Not specified')}

### Exit Conditions
{results.get('exit_conditions', 'Not specified')}

### Parameters
```json
{json.dumps(results.get('params', {}), indent=2)}
```

---

## Validation Results

### MCPT Significance
- **p-value**: {results.get('p_value', 'N/A')}
- **Significant**: {'Yes' if results.get('p_value', 1) < 0.05 else 'No'}
- **Permutations**: {results.get('n_permutations', 1000)}

### Walk-Forward Validation
| Split | In-Sample | Out-of-Sample |
|-------|-----------|---------------|
{generate_wf_table(results.get('walk_forward', []))}

### Sharpe Confidence Interval
- **95% CI**: [{results.get('sharpe_ci_lower', 'N/A'):.2f}, {results.get('sharpe_ci_upper', 'N/A'):.2f}]
- **Point Estimate**: {results.get('val_sharpe', 'N/A'):.2f}

---

## Performance Analysis

### Returns Distribution
{generate_returns_histogram(results.get('returns', []))}

### Drawdown Analysis
- **Max Drawdown**: {results.get('max_drawdown', 'N/A'):.1%}
- **Avg Drawdown**: {results.get('avg_drawdown', 'N/A'):.1%}
- **Recovery Time**: {results.get('avg_recovery_days', 'N/A'):.0f} days

### Monthly Returns
{generate_monthly_returns_table(results.get('monthly_returns', {}))}

---

## Risk Metrics

| Metric | Value |
|--------|-------|
| Volatility (Ann.) | {results.get('volatility', 'N/A'):.1%} |
| Sortino Ratio | {results.get('sortino', 'N/A'):.2f} |
| Calmar Ratio | {results.get('calmar', 'N/A'):.2f} |
| Beta | {results.get('beta', 'N/A'):.2f} |
| Tail Risk (VaR 95%) | {results.get('var_95', 'N/A'):.1%} |

---

## PDT Compliance (Budget Account)

| Holding Period | Sharpe | PDT Compliant |
|----------------|--------|---------------|
{generate_pdt_table(results.get('pdt_results', {}))}

**Recommended**: {results.get('recommended_holding', 2)} day minimum hold

---

## Transaction Cost Analysis

| Cost (bps) | Sharpe | Change |
|------------|--------|--------|
{generate_cost_table(results.get('cost_analysis', {}))}

---

## Regime Analysis

| Regime | Sharpe | Win Rate | Trades |
|--------|--------|----------|--------|
{generate_regime_table(results.get('regime_analysis', {}))}

---

## Critic Validation

| Check | Status |
|-------|--------|
| Lookahead Bias | {'PASS' if results.get('no_lookahead') else 'FAIL'} |
| Overfitting | {'PASS' if results.get('not_overfit') else 'FAIL'} |
| Signal Timing | {'PASS' if results.get('timing_ok') else 'FAIL'} |
| Statistical Significance | {'PASS' if results.get('p_value', 1) < 0.05 else 'FAIL'} |

---

## Next Steps

{generate_next_steps(results)}

---

## Appendix

### Research Cycle
- **Cycle ID**: {results.get('research_cycle', 'N/A')}
- **Run Date**: {results.get('research_date', 'N/A')}

### Data
- **Training Period**: {results.get('train_start', 'N/A')} to {results.get('train_end', 'N/A')}
- **Validation Period**: {results.get('val_start', 'N/A')} to {results.get('val_end', 'N/A')}
- **Data Points**: {results.get('n_datapoints', 'N/A')}

### Files
- Research: `~/quant_results/comprehensive_research/{results.get('research_cycle', '')}.json`
- Validation: `~/quant_results/validation_reports/`
- Config: `config/strategies/validated_strategies.yaml`
"""
    return report
```

## Research Cycle Report

```python
def generate_research_report(cycle_id):
    """
    Generate summary of a research cycle.
    """
    cycle_path = paths.base / f"comprehensive_research/{cycle_id}.json"

    with open(cycle_path) as f:
        cycle = json.load(f)

    report = f"""# Research Cycle Report: {cycle_id}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Runtime**: {cycle.get('runtime_minutes', 0):.1f} minutes

---

## Summary

| Metric | Value |
|--------|-------|
| Total Experiments | {cycle.get('total_experiments', 0)} |
| Significant (p<0.05) | {cycle.get('significant_count', 0)} |
| Production Ready | {cycle.get('passed_all_checks_count', 0)} |

---

## Top Strategies

| Strategy | Symbol | Sharpe | p-value | Status |
|----------|--------|--------|---------|--------|
"""

    for strat in cycle.get('best_strategies', [])[:10]:
        status = "READY" if strat.get('passes_all_checks') else "REVIEW"
        report += f"| {strat['strategy']} | {strat['symbol']} | {strat.get('val_sharpe', 0):.2f} | {strat.get('mcpt_p_value', 1):.4f} | {status} |\n"

    report += f"""
---

## Sector Performance

| Sector | Tested | Significant | Best Sharpe |
|--------|--------|-------------|-------------|
"""

    for sector, data in cycle.get('sector_performance', {}).items():
        report += f"| {sector} | {data.get('total', 0)} | {data.get('significant', 0)} | {data.get('best_sharpe', 0):.2f} |\n"

    report += f"""
---

## Experiment Leads (Next Steps)

"""

    for i, lead in enumerate(cycle.get('experiment_leads', [])[:5], 1):
        report += f"""### {i}. {lead.get('title', 'Untitled')}

- **Strategy**: {lead.get('strategy_type', 'N/A')}
- **Symbols**: {', '.join(lead.get('symbols', []))}
- **Priority**: {lead.get('priority', 0):.1f}
- **Rationale**: {lead.get('rationale', 'N/A')}

"""

    return report
```

## Performance Report

```python
def generate_performance_report(days=30):
    """
    Generate trading performance report.
    """
    from src.execution.broker.alpaca import AlpacaBroker

    broker = AlpacaBroker()
    account = broker.get_account()
    positions = broker.get_positions()

    report = f"""# Performance Report

**Period**: Last {days} days
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Account Summary

| Metric | Value |
|--------|-------|
| Equity | ${float(account.equity):,.2f} |
| Cash | ${float(account.cash):,.2f} |
| Buying Power | ${float(account.buying_power):,.2f} |
| Day Trades Used | {account.daytrade_count}/3 |

---

## Current Positions

| Symbol | Qty | Entry | Current | P&L | P&L % |
|--------|-----|-------|---------|-----|-------|
"""

    for pos in positions:
        pnl_pct = (float(pos.current_price) - float(pos.avg_entry_price)) / float(pos.avg_entry_price) * 100
        report += f"| {pos.symbol} | {int(pos.qty)} | ${float(pos.avg_entry_price):.2f} | ${float(pos.current_price):.2f} | ${float(pos.unrealized_pl):,.2f} | {pnl_pct:+.1f}% |\n"

    report += f"""
---

## Strategy Performance

{generate_strategy_leaderboard(days)}

---

## Risk Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Portfolio Drawdown | {get_portfolio_drawdown():.1%} | {'OK' if get_portfolio_drawdown() < 0.10 else 'WARNING'} |
| Daily VaR (95%) | {get_portfolio_var():.1%} | OK |
| Sharpe (30d) | {get_portfolio_sharpe(30):.2f} | {'OK' if get_portfolio_sharpe(30) > 0.5 else 'REVIEW'} |

---

## Alerts

{generate_alerts()}

"""

    return report
```

## Figure Generation

```python
import matplotlib.pyplot as plt
import numpy as np

def generate_equity_curve(returns, title="Equity Curve"):
    """
    Generate equity curve figure.
    """
    cumulative = (1 + returns).cumprod()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(cumulative.index, cumulative.values, 'b-', linewidth=1.5)
    ax.fill_between(cumulative.index, 1, cumulative.values,
                    where=cumulative.values >= 1, alpha=0.3, color='green')
    ax.fill_between(cumulative.index, 1, cumulative.values,
                    where=cumulative.values < 1, alpha=0.3, color='red')
    ax.axhline(y=1, color='black', linestyle='--', alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Return')

    output_path = paths.base / "figures"
    output_path.mkdir(exist_ok=True)
    fig.savefig(output_path / f"equity_curve_{datetime.now().strftime('%Y%m%d')}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)

    return output_path / f"equity_curve_{datetime.now().strftime('%Y%m%d')}.png"


def generate_drawdown_chart(returns, title="Drawdown"):
    """
    Generate drawdown chart.
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(drawdown.index, 0, drawdown.values, alpha=0.7, color='red')
    ax.set_title(title)
    ax.set_xlabel('Date')
    ax.set_ylabel('Drawdown')

    output_path = paths.base / "figures"
    output_path.mkdir(exist_ok=True)
    fig.savefig(output_path / f"drawdown_{datetime.now().strftime('%Y%m%d')}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)

    return output_path / f"drawdown_{datetime.now().strftime('%Y%m%d')}.png"


def generate_monthly_heatmap(returns, title="Monthly Returns"):
    """
    Generate monthly returns heatmap.
    """
    monthly = returns.resample('M').apply(lambda x: (1 + x).prod() - 1)
    monthly_df = monthly.to_frame('returns')
    monthly_df['year'] = monthly_df.index.year
    monthly_df['month'] = monthly_df.index.month

    pivot = monthly_df.pivot(index='year', columns='month', values='returns')

    fig, ax = plt.subplots(figsize=(14, 6))
    im = ax.imshow(pivot.values * 100, cmap='RdYlGn', aspect='auto', vmin=-10, vmax=10)

    ax.set_xticks(range(12))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    plt.colorbar(im, label='Return (%)')
    ax.set_title(title)

    output_path = paths.base / "figures"
    output_path.mkdir(exist_ok=True)
    fig.savefig(output_path / f"monthly_heatmap_{datetime.now().strftime('%Y%m%d')}.png", dpi=150, bbox_inches='tight')
    plt.close(fig)

    return output_path / f"monthly_heatmap_{datetime.now().strftime('%Y%m%d')}.png"
```

## Saving Reports

```python
def save_report(report_content, report_type, name):
    """
    Save report to appropriate location.
    """
    output_dirs = {
        'strategy': '~/quant_results/strategy_reports',
        'research': '~/quant_results/research_reports',
        'performance': '~/quant_results/performance_reports',
        'validation': '~/quant_results/validation_reports',
    }

    output_dir = paths.base / 'reports'
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{report_type}_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path = output_dir / filename

    with open(output_path, 'w') as f:
        f.write(report_content)

    print(f"Report saved to: {output_path}")
    return output_path
```

## Output Locations

| Report Type | Path |
|-------------|------|
| Strategy Reports | `~/quant_results/strategy_reports/` |
| Research Reports | `~/quant_results/research_reports/` |
| Performance Reports | `~/quant_results/performance_reports/` |
| Validation Reports | `~/quant_results/validation_reports/` |
| Figures | `~/quant_results/figures/` |
