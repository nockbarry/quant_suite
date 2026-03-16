#!/usr/bin/env python3
"""Run meta-observer analysis across all Athena instances.

Discovers all instance directories, snapshots their state,
computes cross-instance divergence metrics, and generates recommendations.

Usage:
    PYTHONPATH=. python scripts/run_meta_observer.py
    PYTHONPATH=. python scripts/run_meta_observer.py --instances ~/quant_results,~/quant_results_alpha
"""

import argparse
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from src.parallel.meta_observer import MetaObserver


def main():
    parser = argparse.ArgumentParser(
        description="Run meta-observer analysis across Athena instances"
    )
    parser.add_argument(
        "--instances",
        type=str,
        default=None,
        help="Comma-separated list of instance result directories "
             "(default: auto-discover ~/quant_results*)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full JSON report instead of summary",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    # Parse instance dirs
    instance_dirs = None
    if args.instances:
        instance_dirs = [Path(d.strip()).expanduser() for d in args.instances.split(",")]

    observer = MetaObserver(instance_dirs=instance_dirs)

    print(f"Discovered {len(observer.instance_dirs)} instance(s):")
    for d in observer.instance_dirs:
        print(f"  - {d}")
    print()

    metrics = observer.run()

    if args.json:
        import json
        print(json.dumps(asdict(metrics), indent=2, default=str))
        return

    # Print summary
    print(f"={'=' * 60}")
    print(f"  META-OBSERVER REPORT  ({metrics.timestamp[:19]})")
    print(f"  {metrics.num_instances} instance(s) analyzed")
    print(f"={'=' * 60}")
    print()

    # Instance summary
    print("INSTANCES:")
    for inst in metrics.instances:
        print(
            f"  {inst['name']:>12s}  |  "
            f"Equity: ${inst['equity']:>10,.0f}  |  "
            f"Positions: {inst['positions']:>3d}  |  "
            f"Theses: {inst['theses']:>2d}  |  "
            f"Accuracy: {inst.get('prediction_accuracy', 0):>4.0f}%"
        )
    print()

    # Thesis overlap
    print(f"THESIS OVERLAP:  Jaccard = {metrics.thesis_overlap_jaccard:.1%}")
    if metrics.shared_theses:
        print(f"  Shared ({len(metrics.shared_theses)}): {', '.join(metrics.shared_theses[:10])}")
        if len(metrics.shared_theses) > 10:
            print(f"    ... and {len(metrics.shared_theses) - 10} more")
    if metrics.unique_theses:
        print(f"  Unique:")
        for inst, names in metrics.unique_theses.items():
            print(f"    {inst}: {', '.join(names[:5])}")
    print()

    # Position convergence
    print(f"POSITION CONVERGENCE:  Jaccard = {metrics.position_overlap_jaccard:.1%}")
    print(f"  Agreement rate: {metrics.position_agreement_rate:.0%} of symbols held by 2+ instances")
    if metrics.consensus_positions:
        print(f"  Consensus ({len(metrics.consensus_positions)}): {', '.join(metrics.consensus_positions[:15])}")
        if len(metrics.consensus_positions) > 15:
            print(f"    ... and {len(metrics.consensus_positions) - 15} more")
    if metrics.divergent_positions:
        print(f"  Divergent:")
        for inst, syms in metrics.divergent_positions.items():
            print(f"    {inst}: {', '.join(syms[:10])}")
    print()

    # Conviction distributions
    if metrics.thesis_conviction_distributions:
        print("CONVICTION DISTRIBUTIONS (shared theses):")
        for name, dist in sorted(
            metrics.thesis_conviction_distributions.items(),
            key=lambda x: -x[1]["std"],
        )[:10]:
            bar_fill = int(dist["mean"] / 5)  # 20-char bar for 100%
            bar = "#" * bar_fill + "-" * (20 - bar_fill)
            print(
                f"  {name[:35]:35s}  [{bar}]  "
                f"{dist['mean']:5.1f}% +/- {dist['std']:4.1f}%  "
                f"(range: {dist['min']:.0f}-{dist['max']:.0f}%)"
            )
        print()

    # Equity comparison
    if len(metrics.equity_comparison) >= 2:
        equities = list(metrics.equity_comparison.values())
        best_name = max(metrics.equity_comparison, key=metrics.equity_comparison.get)
        worst_name = min(metrics.equity_comparison, key=metrics.equity_comparison.get)
        spread = (max(equities) - min(equities)) / max(equities) * 100 if max(equities) > 0 else 0
        print(f"EQUITY COMPARISON:  Spread = {spread:.1f}%")
        print(f"  Best:  {best_name} (${metrics.equity_comparison[best_name]:,.0f})")
        print(f"  Worst: {worst_name} (${metrics.equity_comparison[worst_name]:,.0f})")
        print()

    # Recommendations
    print("RECOMMENDATIONS:")
    for i, rec in enumerate(metrics.recommendations, 1):
        print(f"  {i}. {rec}")
    print()


if __name__ == "__main__":
    main()
