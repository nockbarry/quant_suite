#!/usr/bin/env python3
"""
Validate Congressional Trade Signal Quality.

Analyzes the information value of congressional trading signals
based on historical study results and current system implementation.

Usage:
    python3 scripts/validate_congressional_signal.py
"""

import json
import logging
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from src.core.paths import paths


def load_study_results() -> dict:
    """Load existing congressional study results."""
    study_file = Path.home() / "quant_archive/congressional_study/full_timing_study_results.json"
    if study_file.exists():
        with open(study_file) as f:
            return json.load(f)
    return {}


def analyze_signal_quality(study_results: dict) -> dict:
    """Analyze if congressional signal is worth using."""
    analysis = {
        "timestamp": datetime.now().isoformat(),
        "signal_type": "congressional",
        "verdict": "NOT_RECOMMENDED",
        "metrics": {},
        "recommendations": [],
    }

    if not study_results:
        analysis["error"] = "No study results found"
        return analysis

    # Extract key metrics
    pre_disc = study_results.get("pre_disclosure_analysis", {})
    post_disc = study_results.get("post_disclosure_analysis", {})
    politicians = study_results.get("politician_performance", [])

    # Pre-disclosure (information advantage)
    purchases = pre_disc.get("purchases", {})
    sales = pre_disc.get("sales", {})

    analysis["metrics"]["pre_disclosure"] = {
        "purchase_hit_rate": purchases.get("hit_rate", 0),
        "sale_hit_rate": sales.get("hit_rate", 0),
        "purchase_p_value": purchases.get("p_value", 1),
        "sale_p_value": sales.get("p_value", 1),
        "info_advantage_score": study_results.get("summary", {}).get("information_advantage_score", 0),
    }

    # Post-disclosure (following strategy)
    analysis["metrics"]["post_disclosure"] = post_disc.get("following_strategy_return_20d", 0)

    # Politician filtering potential
    top_performers = [p for p in politicians if p.get("hit_rate", 0) >= 0.6]
    analysis["metrics"]["high_hit_rate_politicians"] = len(top_performers)

    # Decision logic
    info_adv = analysis["metrics"]["pre_disclosure"]["info_advantage_score"]
    following_ret = analysis["metrics"]["post_disclosure"]

    if info_adv < -5:
        analysis["verdict"] = "CONTRARIAN_POTENTIAL"
        analysis["recommendations"].append(
            "Consider contrarian strategy - fade congressional trades"
        )
    elif info_adv > 2 and following_ret > 0.5:
        analysis["verdict"] = "RECOMMENDED"
        analysis["recommendations"].append(
            "Congressional signal shows edge - include in composite"
        )
    elif len(top_performers) >= 5:
        analysis["verdict"] = "SELECTIVE"
        analysis["recommendations"].append(
            f"Track {len(top_performers)} high-hit-rate politicians only"
        )
        analysis["top_politicians"] = [
            {"name": p.get("politician"), "hit_rate": p.get("hit_rate")}
            for p in top_performers[:10]
        ]
    else:
        analysis["verdict"] = "NOT_RECOMMENDED"
        analysis["recommendations"].append(
            "Congressional signal shows no edge - deprioritize"
        )

    # Cluster signal recommendation
    analysis["recommendations"].append(
        "CLUSTER SIGNAL: Alert when 3+ politicians trade same stock within 14 days"
    )

    return analysis


def print_report(analysis: dict) -> None:
    """Print validation report."""
    print("\n" + "=" * 70)
    print("CONGRESSIONAL SIGNAL VALIDATION REPORT")
    print("=" * 70)

    print(f"\nVerdict: {analysis['verdict']}")

    print("\nPre-Disclosure Metrics (Information Advantage):")
    pre = analysis["metrics"].get("pre_disclosure", {})
    print(f"  Purchase Hit Rate: {pre.get('purchase_hit_rate', 0):.1%}")
    print(f"  Sale Hit Rate: {pre.get('sale_hit_rate', 0):.1%}")
    print(f"  Purchase P-Value: {pre.get('purchase_p_value', 0):.4f}")
    print(f"  Sale P-Value: {pre.get('sale_p_value', 0):.4f}")
    print(f"  Information Advantage Score: {pre.get('info_advantage_score', 0):.2f}%")

    print(f"\nPost-Disclosure (Following) Return: {analysis['metrics'].get('post_disclosure', 0):.2f}%")
    print(f"High Hit-Rate Politicians: {analysis['metrics'].get('high_hit_rate_politicians', 0)}")

    print("\nRecommendations:")
    for rec in analysis.get("recommendations", []):
        print(f"  - {rec}")

    if "top_politicians" in analysis:
        print("\nTop Politicians to Track:")
        for p in analysis["top_politicians"]:
            print(f"  - {p['name']}: {p['hit_rate']:.0%} hit rate")

    print("\n" + "=" * 70)

    # Final recommendation
    if analysis["verdict"] == "NOT_RECOMMENDED":
        print("\nACTION: Deprioritize congressional signals in trade decisions.")
        print("Focus on cluster detection only.")
    elif analysis["verdict"] == "SELECTIVE":
        print("\nACTION: Filter congressional signals by politician performance.")
        print("Only use signals from high hit-rate politicians.")
    else:
        print(f"\nACTION: {analysis['verdict']}")

    print("")


def update_signal_quality_rules(analysis: dict) -> None:
    """Update signal quality rules based on analysis."""
    rules_file = paths.knowledge / "signal_rules.yaml"
    rules_file.parent.mkdir(parents=True, exist_ok=True)

    import yaml

    rules = {}
    if rules_file.exists():
        with open(rules_file) as f:
            rules = yaml.safe_load(f) or {}

    rules["congressional"] = {
        "verdict": analysis["verdict"],
        "validated_at": analysis["timestamp"],
        "recommended_weight": 0.1 if analysis["verdict"] == "NOT_RECOMMENDED" else 0.3,
        "use_cluster_only": analysis["verdict"] == "NOT_RECOMMENDED",
        "recommendations": analysis.get("recommendations", []),
    }

    with open(rules_file, "w") as f:
        yaml.dump(rules, f, default_flow_style=False)

    logger.info(f"Updated signal rules at {rules_file}")


def main():
    logger.info("Loading congressional study results...")
    study_results = load_study_results()

    logger.info("Analyzing signal quality...")
    analysis = analyze_signal_quality(study_results)

    print_report(analysis)

    logger.info("Updating signal quality rules...")
    update_signal_quality_rules(analysis)

    # Save analysis
    output_file = paths.validation_reports / "congressional_signal_validation.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(analysis, f, indent=2)
    logger.info(f"Validation report saved to {output_file}")


if __name__ == "__main__":
    main()
