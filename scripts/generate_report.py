#!/usr/bin/env python3
"""
Report Generation Script.

Generate comprehensive reports for strategies, research cycles, and performance.

Usage:
    PYTHONPATH=. python scripts/generate_report.py --type strategy --name bollinger_reversal --symbol QCOM
    PYTHONPATH=. python scripts/generate_report.py --type research --cycle cycle_20260103_195257
    PYTHONPATH=. python scripts/generate_report.py --type performance --days 30
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.core.paths import paths

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def generate_strategy_report(strategy_name: str, symbol: str) -> str:
    """Generate comprehensive strategy report."""

    # Load validation results if available
    validation_dir = paths.validation_reports
    validation_files = sorted(validation_dir.glob(f"validation_{strategy_name}_{symbol}_*.json"))

    validation = {}
    if validation_files:
        with open(validation_files[-1]) as f:
            validation = json.load(f)

    # Load research results
    research_dir = paths.comprehensive_research
    # Exclude _leads.json files which have different structure
    research_files = sorted([f for f in research_dir.glob("cycle_*.json") if "_leads" not in f.name])

    research = {}
    for rf in research_files:
        with open(rf) as f:
            cycle = json.load(f)
            if not isinstance(cycle, dict):
                continue
            for strat in cycle.get('best_strategies', []):
                if strat['strategy'] == strategy_name and strat['symbol'] == symbol:
                    research = strat
                    research['cycle_id'] = cycle['cycle_id']
                    break
        if research:
            break

    report = f"""# Strategy Report: {strategy_name} on {symbol}

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Status**: {'VALIDATED' if validation.get('passed') else 'RESEARCH'}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Validation Sharpe | {research.get('val_sharpe', 'N/A')} |
| MCPT p-value | {research.get('mcpt_p_value', 'N/A')} |
| Passes All Checks | {'Yes' if research.get('passes_all_checks') else 'No'} |

---

## Validation Results

"""

    if validation:
        report += "| Check | Status |\n|-------|--------|\n"
        for check, passed in validation.get('checks', {}).items():
            status = 'PASS' if passed else 'FAIL'
            report += f"| {check} | {status} |\n"

        report += f"\n**Recommendation**: {validation.get('recommendation', 'N/A')}\n"

        if validation.get('issues'):
            report += "\n### Issues\n"
            for issue in validation['issues']:
                report += f"- {issue}\n"

    report += f"""
---

## Research Cycle

- **Cycle ID**: {research.get('cycle_id', 'N/A')}
- **Train Sharpe**: {research.get('train_sharpe', 'N/A')}
- **Validation Sharpe**: {research.get('val_sharpe', 'N/A')}
- **Sharpe CI**: {research.get('sharpe_ci', 'N/A')}

---

## Next Steps

1. Run /critic validation if not done
2. Test with /validate for full suite
3. Use /promote to move to paper trading
4. Monitor with /monitor skill

---

## Files

- Validation: `{validation_files[-1] if validation_files else 'Not available'}`
- Research: `{paths.comprehensive_research}/{research.get('cycle_id', '')}.json`
"""

    return report


def generate_research_report(cycle_id: str) -> str:
    """Generate research cycle summary report."""

    cycle_path = paths.comprehensive_research / f"{cycle_id}.json"

    if not cycle_path.exists():
        return f"# Error\n\nCycle not found: {cycle_id}"

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

## Experiment Leads

"""

    for i, lead in enumerate(cycle.get('experiment_leads', [])[:5], 1):
        report += f"""### {i}. {lead.get('title', 'Untitled')}
- **Strategy**: {lead.get('strategy_type', 'N/A')}
- **Symbols**: {', '.join(lead.get('symbols', []))}
- **Priority**: {lead.get('priority', 0):.1f}
- **Rationale**: {lead.get('rationale', 'N/A')}

"""

    return report


def generate_performance_report(days: int = 30) -> str:
    """Generate trading performance report."""

    report = f"""# Performance Report

**Period**: Last {days} days
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Portfolio Summary

"""

    try:
        from src.execution.broker.alpaca import AlpacaBroker
        broker = AlpacaBroker()
        account = broker.get_account()
        positions = broker.get_positions()

        report += f"""| Metric | Value |
|--------|-------|
| Equity | ${float(account.equity):,.2f} |
| Cash | ${float(account.cash):,.2f} |
| Day Trades Used | {account.daytrade_count}/3 |

---

## Current Positions

| Symbol | Qty | Entry | Current | P&L |
|--------|-----|-------|---------|-----|
"""

        for pos in positions:
            report += f"| {pos.symbol} | {int(pos.qty)} | ${float(pos.avg_entry_price):.2f} | ${float(pos.current_price):.2f} | ${float(pos.unrealized_pl):,.2f} |\n"

    except Exception as e:
        report += f"*Could not connect to broker: {e}*\n"

    # Load tracked insights
    report += """
---

## Recent Insights

"""

    try:
        from workflows.research.session_tracker import get_tracker
        tracker = get_tracker()
        summary = tracker.generate_summary_report()

        report += f"""| Category | Count |
|----------|-------|
| Total Insights | {summary['totals']['insights']} |
| Total Experiments | {summary['totals']['experiments']} |
| Successful Strategies | {summary['totals']['successful_strategies']} |
| Actionable Insights | {summary['actionable_insights']} |
"""

    except Exception as e:
        report += f"*Could not load tracker: {e}*\n"

    return report


def save_report(content: str, report_type: str, name: str) -> Path:
    """Save report to file."""

    output_dirs = {
        'strategy': paths.strategy_reports,
        'research': paths.research_reports,
        'performance': paths.performance_reports,
    }

    output_dir = output_dirs.get(report_type, paths.base / "reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{report_type}_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    output_path = output_dir / filename

    with open(output_path, 'w') as f:
        f.write(content)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate reports")
    parser.add_argument("--type", required=True, choices=['strategy', 'research', 'performance'],
                       help="Report type")
    parser.add_argument("--name", help="Strategy name (for strategy report)")
    parser.add_argument("--symbol", help="Symbol (for strategy report)")
    parser.add_argument("--cycle", help="Cycle ID (for research report)")
    parser.add_argument("--days", type=int, default=30, help="Days (for performance report)")

    args = parser.parse_args()

    if args.type == 'strategy':
        if not args.name or not args.symbol:
            parser.error("--name and --symbol required for strategy report")
        content = generate_strategy_report(args.name, args.symbol)
        name = f"{args.name}_{args.symbol}"

    elif args.type == 'research':
        if not args.cycle:
            parser.error("--cycle required for research report")
        content = generate_research_report(args.cycle)
        name = args.cycle

    elif args.type == 'performance':
        content = generate_performance_report(args.days)
        name = f"perf_{args.days}d"

    output_path = save_report(content, args.type, name)

    print(f"Report saved to: {output_path}")
    print("\n" + content)

    return 0


if __name__ == "__main__":
    exit(main())
