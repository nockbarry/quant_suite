#!/usr/bin/env python3
"""Log alpha discovery scan results to knowledge base."""

import json
from datetime import datetime
from pathlib import Path

from workflows.research.knowledge_base import KnowledgeBase


def main():
    """Log scan findings to knowledge base."""

    kb = KnowledgeBase()

    # Load latest scan results
    scan_dir = Path.home() / "quant_results" / "alpha_discovery"
    latest_scan = sorted(scan_dir.glob("monday_scan_*.json"))[-1]

    with open(latest_scan, 'r') as f:
        scan_data = json.load(f)

    print(f"Logging scan from: {latest_scan.name}")

    # Record the scan as a data source
    symbols_scanned = []
    for idea in scan_data['trade_ideas']:
        symbols_scanned.append(idea['symbol'])

    kb.record_data_source_performance(
        source='market_scanner',
        source_type='alpha_discovery',
        prediction_correct=None,  # Will validate later
        alpha_generated=scan_data['market_summary']['avg_expected_edge'],
        strategy_name='mean_reversion',
        sharpe=0.0,  # Not yet backtested
        symbols=symbols_scanned[:5],
        notes=f"Found {len(scan_data['trade_ideas'])} opportunities for Monday 2026-01-06"
    )

    print(f"Logged scan to knowledge base")
    print(f"Top opportunities: {', '.join(symbols_scanned[:5])}")
    print("Knowledge base updated successfully")


if __name__ == "__main__":
    main()
