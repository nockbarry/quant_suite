#!/usr/bin/env python3
"""Run portfolio stress test and print results.

Usage:
    PYTHONPATH=. python scripts/run_stress_test.py
    PYTHONPATH=. python scripts/run_stress_test.py --json   # Machine-readable output
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.risk.stress_tester import PortfolioStressTester


def main():
    parser = argparse.ArgumentParser(description="Portfolio stress test")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    tester = PortfolioStressTester()
    report = tester.run_full_report()

    if args.json:
        print(json.dumps(asdict(report), indent=2))
        return

    # Pretty print
    print("=" * 70)
    print(f"  PORTFOLIO STRESS TEST  —  {report.timestamp[:19]}")
    print("=" * 70)
    print(f"  Equity: ${report.portfolio_equity:,.0f}  |  Cash: ${report.cash:,.0f}  |  Positions: {report.position_count}")
    print()

    # Scenario results
    print("  SCENARIO ANALYSIS")
    print("  " + "-" * 66)
    print(f"  {'Scenario':<32} {'Impact %':>10} {'Impact $':>12} {'Affected':>8}")
    print("  " + "-" * 66)
    for sr in report.scenario_results:
        impact_pct = sr["portfolio_impact_pct"]
        impact_usd = sr["portfolio_impact_usd"]
        marker = "!!" if abs(impact_pct) > 10 else "  "
        print(
            f"{marker}{sr['scenario_name']:<32} "
            f"{impact_pct:>+9.1f}% "
            f"${impact_usd:>+11,.0f} "
            f"{sr['positions_affected']:>8}"
        )
        if sr["worst_position"]:
            print(f"    worst: {sr['worst_position']} ${sr['worst_position_loss_usd']:+,.0f}  |  "
                  f"best: {sr['best_position']} ${sr['best_position_gain_usd']:+,.0f}")
    print()

    # VaR metrics
    print("  RISK METRICS")
    print("  " + "-" * 40)
    print(f"  95% VaR (1-day):       {report.var_95_pct:>6.2f}%  (${report.var_95_pct/100*report.portfolio_equity:>+,.0f})")
    print(f"  99% VaR (1-day):       {report.var_99_pct:>6.2f}%  (${report.var_99_pct/100*report.portfolio_equity:>+,.0f})")
    print(f"  Expected Shortfall:    {report.expected_shortfall_pct:>6.2f}%  (${report.expected_shortfall_pct/100*report.portfolio_equity:>+,.0f})")
    print(f"  Concentration (HHI):   {report.concentration_risk_score:>6.3f}")
    print(f"  Max sector exposure:   {report.max_single_sector_exposure_pct:>6.1f}%")
    print(f"  Max single position:   {report.max_single_position_pct:>6.1f}%")
    print()

    # Sector weights
    if report.sector_weights:
        print("  SECTOR WEIGHTS")
        print("  " + "-" * 40)
        for sector, pct in report.sector_weights.items():
            bar = "#" * int(pct / 2)
            flag = " <<" if pct > 40 else ""
            print(f"  {sector:<16} {pct:>5.1f}%  {bar}{flag}")
        print()

    # Recommendations
    if report.recommendations:
        print("  RECOMMENDATIONS")
        print("  " + "-" * 40)
        for i, rec in enumerate(report.recommendations, 1):
            print(f"  {i}. {rec}")
        print()

    print("=" * 70)


if __name__ == "__main__":
    main()
