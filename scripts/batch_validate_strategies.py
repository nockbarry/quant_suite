#!/usr/bin/env python3
"""Batch Strategy Validation Script.

Runs MCPT validation on multiple strategy-symbol pairs and consolidates results.

Usage:
    PYTHONPATH=. python scripts/batch_validate_strategies.py
    PYTHONPATH=. python scripts/batch_validate_strategies.py --quick
    PYTHONPATH=. python scripts/batch_validate_strategies.py --parallel 4
    PYTHONPATH=. python scripts/batch_validate_strategies.py --category technical
"""

import argparse
import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from src.core.paths import paths

# Import the validation function from existing script
from scripts.validate_strategy import run_validation, ValidationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Strategy-symbol pairs to validate, organized by category
VALIDATION_TARGETS = {
    "technical": [
        ("bollinger_reversal", ["QCOM", "MU", "MRVL", "AMD", "IWM"]),
        ("momentum", ["AMD", "NVDA", "QQQ"]),
        ("rsi_reversal", ["IWM", "SPY", "XLF"]),
        ("breakout", ["IWM", "QQQ", "XLE"]),
        ("mean_reversion", ["SPY", "IWM", "XLF"]),
    ],
    "alternative": [
        ("congressional_cluster", ["QQQ", "XLF", "XLE"]),
        ("insider_follow", ["QQQ", "IWM", "XLF"]),
        ("sentiment_contrarian", ["SPY", "QQQ", "IWM"]),
        ("options_flow", ["SPY", "QQQ", "NVDA"]),
        ("short_squeeze", ["IWM", "XRT", "ARKK"]),
    ],
    "sector": [
        ("sector_rotation", ["SPY", "QQQ", "IWM"]),
        ("energy_mean_reversion", ["XLE", "OXY", "SLB"]),
        ("earnings_momentum", ["AAPL", "MSFT", "NVDA"]),
        ("fed_announcement", ["XLF", "TLT", "SPY"]),
        ("vix_mean_reversion", ["SPY", "QQQ", "VXX"]),
    ],
    "composite": [
        ("multi_signal", ["AMD", "NVDA", "IWM"]),
        ("regime_adaptive", ["SPY", "QQQ", "IWM"]),
        ("factor_momentum", ["SPY", "IWM", "QQQ"]),
        ("quality_momentum", ["QQQ", "SPY", "IWM"]),
        ("value_momentum", ["IWM", "XLF", "XLE"]),
    ],
}


def validate_single(strategy: str, symbol: str, quick: bool = False) -> Optional[dict]:
    """Validate a single strategy-symbol pair.

    Args:
        strategy: Strategy name
        symbol: Symbol to test
        quick: Use fewer permutations

    Returns:
        Dictionary with validation results or None if failed
    """
    try:
        logger.info(f"Validating {strategy}/{symbol}...")
        result = run_validation(strategy, symbol, quick=quick, generate_plots=False)
        return {
            "strategy": strategy,
            "symbol": symbol,
            "sharpe": result.metrics.get("mcpt_sharpe", 0),
            "p_value": result.metrics.get("mcpt_p_value", 1),
            "oos_sharpe": result.metrics.get("oos_sharpe", 0),
            "validated": result.metrics.get("mcpt_p_value", 1) < 0.05,
            "recommendation": result.recommendation,
            "checks_passed": sum(result.checks.values()),
            "checks_total": len(result.checks),
            "issues": result.issues,
            "validated_at": result.validated_at,
        }
    except Exception as e:
        logger.error(f"Failed to validate {strategy}/{symbol}: {e}")
        return {
            "strategy": strategy,
            "symbol": symbol,
            "sharpe": 0,
            "p_value": 1,
            "oos_sharpe": 0,
            "validated": False,
            "recommendation": "ERROR",
            "error": str(e),
            "validated_at": datetime.now().isoformat(),
        }


def run_batch_validation(
    categories: Optional[list[str]] = None,
    quick: bool = False,
    parallel: int = 1,
) -> dict:
    """Run batch validation on all strategy-symbol pairs.

    Args:
        categories: List of categories to validate (None = all)
        quick: Use fewer permutations
        parallel: Number of parallel workers (1 = sequential)

    Returns:
        Dictionary with all validation results
    """
    # Collect all targets
    targets = []
    for category, strategies in VALIDATION_TARGETS.items():
        if categories and category not in categories:
            continue
        for strategy, symbols in strategies:
            for symbol in symbols:
                targets.append((strategy, symbol))

    logger.info(f"Validating {len(targets)} strategy-symbol pairs...")

    results = []

    if parallel > 1:
        try:
            from joblib import Parallel, delayed

            results = Parallel(n_jobs=parallel)(
                delayed(validate_single)(strategy, symbol, quick)
                for strategy, symbol in targets
            )
        except ImportError:
            logger.warning("joblib not installed, running sequentially")
            parallel = 1

    if parallel == 1:
        for strategy, symbol in targets:
            result = validate_single(strategy, symbol, quick)
            if result:
                results.append(result)

    # Filter out None results
    results = [r for r in results if r is not None]

    # Organize results by strategy
    by_strategy = {}
    for result in results:
        strategy = result["strategy"]
        symbol = result["symbol"]
        if strategy not in by_strategy:
            by_strategy[strategy] = {}
        by_strategy[strategy][symbol] = {
            "sharpe": round(result["sharpe"], 3),
            "p_value": round(result["p_value"], 4),
            "oos_sharpe": round(result.get("oos_sharpe", 0), 3),
            "validated": result["validated"],
            "recommendation": result["recommendation"],
            "validated_at": result["validated_at"],
        }

    return {
        "validation_run": {
            "timestamp": datetime.now().isoformat(),
            "total_pairs": len(targets),
            "validated_count": sum(1 for r in results if r.get("validated")),
            "categories": categories or list(VALIDATION_TARGETS.keys()),
            "quick_mode": quick,
        },
        "strategies": by_strategy,
        "summary": generate_summary(results),
    }


def generate_summary(results: list[dict]) -> dict:
    """Generate summary statistics from results."""
    validated = [r for r in results if r.get("validated")]
    needs_review = [r for r in results if r.get("recommendation") == "NEEDS_REVIEW"]
    rejected = [r for r in results if r.get("recommendation") == "REJECT"]
    errors = [r for r in results if r.get("recommendation") == "ERROR"]

    # Best performers
    sorted_by_sharpe = sorted(validated, key=lambda x: x.get("sharpe", 0), reverse=True)
    top_5 = [
        {"strategy": r["strategy"], "symbol": r["symbol"], "sharpe": r["sharpe"], "p_value": r["p_value"]}
        for r in sorted_by_sharpe[:5]
    ]

    return {
        "total": len(results),
        "validated": len(validated),
        "needs_review": len(needs_review),
        "rejected": len(rejected),
        "errors": len(errors),
        "validation_rate": round(len(validated) / len(results) * 100, 1) if results else 0,
        "top_5_by_sharpe": top_5,
    }


def save_results(results: dict, output_path: Path) -> None:
    """Save results to YAML file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(results, f, default_flow_style=False, sort_keys=False)
    logger.info(f"Results saved to: {output_path}")


def print_report(results: dict) -> None:
    """Print a summary report."""
    print("\n" + "=" * 70)
    print("BATCH VALIDATION REPORT")
    print("=" * 70)

    run_info = results["validation_run"]
    summary = results["summary"]

    print(f"\nRun: {run_info['timestamp']}")
    print(f"Mode: {'Quick' if run_info['quick_mode'] else 'Full'}")
    print(f"Categories: {', '.join(run_info['categories'])}")

    print(f"\nResults:")
    print(f"  Total pairs tested: {summary['total']}")
    print(f"  Validated (p<0.05): {summary['validated']} ({summary['validation_rate']}%)")
    print(f"  Needs review:       {summary['needs_review']}")
    print(f"  Rejected:           {summary['rejected']}")
    print(f"  Errors:             {summary['errors']}")

    if summary["top_5_by_sharpe"]:
        print(f"\nTop 5 by Sharpe:")
        for i, item in enumerate(summary["top_5_by_sharpe"], 1):
            print(f"  {i}. {item['strategy']}/{item['symbol']}: Sharpe={item['sharpe']:.2f}, p={item['p_value']:.4f}")

    print("\n" + "=" * 70)

    # Detailed by strategy
    print("\nDETAILED RESULTS BY STRATEGY:")
    print("-" * 70)

    for strategy, symbols in results["strategies"].items():
        validated_count = sum(1 for s in symbols.values() if s.get("validated"))
        print(f"\n{strategy} ({validated_count}/{len(symbols)} validated):")
        for symbol, data in symbols.items():
            status = "PASS" if data["validated"] else data["recommendation"]
            print(f"  {symbol}: Sharpe={data['sharpe']:.2f}, p={data['p_value']:.4f} [{status}]")


def main():
    parser = argparse.ArgumentParser(description="Batch validate trading strategies")
    parser.add_argument("--quick", action="store_true", help="Quick mode (fewer permutations)")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers")
    parser.add_argument("--category", nargs="+", choices=list(VALIDATION_TARGETS.keys()),
                        help="Only validate specific categories")
    parser.add_argument("--output", type=str, default=None,
                        help="Output path for results YAML")

    args = parser.parse_args()

    # Run validation
    results = run_batch_validation(
        categories=args.category,
        quick=args.quick,
        parallel=args.parallel,
    )

    # Save results
    output_path = Path(args.output) if args.output else paths.base / "config" / "validated_strategies.yaml"
    save_results(results, output_path)

    # Print report
    print_report(results)

    # Return exit code based on validation success
    if results["summary"]["validated"] > 0:
        return 0
    return 1


if __name__ == "__main__":
    exit(main())
