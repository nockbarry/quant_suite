"""Meta-observer service — reads meta reports for the web dashboard."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)

REPORT_DIR = paths.base / "parallel"


def get_meta_dashboard_data() -> dict:
    """Load meta-observer data for the dashboard.

    Tries to load the latest saved report. If no recent report exists
    (or none at all), runs a quick live analysis.

    Returns:
        Dict with keys: report, instances, position_matrix, conviction_dists,
        recommendations, history.
    """
    report = get_latest_report()

    # If no report exists, try running a fresh analysis
    if report.get("missing"):
        report = run_fresh_analysis()

    # Build position matrix for display
    position_matrix = _build_position_matrix(report)

    # Build conviction distribution list sorted by std desc
    conviction_dists = _build_conviction_list(report)

    return {
        "report": report,
        "instances": report.get("instances", []),
        "position_matrix": position_matrix,
        "conviction_dists": conviction_dists,
        "recommendations": report.get("recommendations", []),
        "history": get_report_history(limit=5),
    }


def get_latest_report() -> dict:
    """Load the most recent meta-observer report.

    Checks for meta_report_latest.json first, then falls back to
    the most recently modified timestamped report.
    """
    # Try latest file first
    latest_path = REPORT_DIR / "meta_report_latest.json"
    if latest_path.exists():
        try:
            with open(latest_path) as f:
                report = json.load(f)
            report["_source"] = str(latest_path)
            _enrich_report(report)
            return report
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to read latest meta report: {e}")

    # Fallback: find most recent timestamped report
    if REPORT_DIR.exists():
        files = sorted(
            REPORT_DIR.glob("meta_report_2*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for f in files[:1]:
            try:
                with open(f) as fh:
                    report = json.load(fh)
                report["_source"] = str(f)
                _enrich_report(report)
                return report
            except (json.JSONDecodeError, ValueError):
                continue

    return {
        "missing": True,
        "message": (
            "No meta-observer reports found. Run: "
            "PYTHONPATH=. python scripts/run_meta_observer.py"
        ),
    }


def run_fresh_analysis() -> dict:
    """Run a fresh meta-observer analysis and return the report as a dict."""
    try:
        from src.parallel.meta_observer import MetaObserver
        from dataclasses import asdict

        observer = MetaObserver()
        if not observer.instance_dirs:
            return {
                "missing": True,
                "message": "No Athena instances discovered. Set up parallel instances first.",
            }

        metrics = observer.run()
        report = asdict(metrics)
        report["_source"] = "live"
        _enrich_report(report)
        return report
    except Exception as e:
        logger.warning(f"Failed to run fresh meta-observer analysis: {e}")
        return {
            "missing": True,
            "message": f"Meta-observer analysis failed: {e}",
        }


def get_report_history(limit: int = 10) -> list:
    """Load recent meta-observer reports (summary only)."""
    if not REPORT_DIR.exists():
        return []

    files = sorted(
        REPORT_DIR.glob("meta_report_2*.json"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]

    results = []
    for f in files:
        try:
            with open(f) as fh:
                report = json.load(fh)
            results.append({
                "timestamp": report.get("timestamp", ""),
                "num_instances": report.get("num_instances", 0),
                "thesis_overlap": report.get("thesis_overlap_jaccard", 0),
                "position_overlap": report.get("position_overlap_jaccard", 0),
                "agreement_rate": report.get("position_agreement_rate", 0),
                "filename": f.name,
            })
        except (json.JSONDecodeError, ValueError):
            continue

    return results


def _build_position_matrix(report: dict) -> list:
    """Build a position-by-instance matrix from report data.

    Returns list of {symbol, instances: [{name, held}], count}.
    """
    if report.get("missing"):
        return []

    instances = report.get("instances", [])
    instance_names = [inst["name"] for inst in instances]

    consensus = set(report.get("consensus_positions", []))
    divergent = report.get("divergent_positions", {})

    # Collect all symbols
    all_symbols = set(consensus)
    for syms in divergent.values():
        all_symbols.update(syms)

    if not all_symbols:
        return []

    matrix = []
    for sym in sorted(all_symbols):
        holders = []
        count = 0
        for name in instance_names:
            held = (
                sym in consensus
                or sym in divergent.get(name, [])
                # Check if symbol is NOT unique to another instance
                or (sym in consensus)
            )
            # More precise: symbol is held by this instance if:
            # - it's in consensus (all hold it), OR
            # - it's in this instance's divergent list
            held = sym in consensus or sym in divergent.get(name, [])
            holders.append({"name": name, "held": held})
            if held:
                count += 1

        matrix.append({
            "symbol": sym,
            "instances": holders,
            "count": count,
        })

    # Sort: most consensus first, then alphabetical
    matrix.sort(key=lambda x: (-x["count"], x["symbol"]))
    return matrix


def _build_conviction_list(report: dict) -> list:
    """Build sorted conviction distribution list for display."""
    dists = report.get("thesis_conviction_distributions", {})
    if not dists:
        return []

    result = []
    for name, dist in dists.items():
        result.append({
            "name": name,
            "mean": dist.get("mean", 0),
            "std": dist.get("std", 0),
            "min": dist.get("min", 0),
            "max": dist.get("max", 0),
            "n_instances": dist.get("n_instances", 0),
            "values": dist.get("values", []),
        })

    # Sort by std descending (highest variance first)
    result.sort(key=lambda x: -x["std"])
    return result


def _enrich_report(report: dict) -> None:
    """Add computed display fields to a report."""
    ts = report.get("timestamp")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            age_seconds = (datetime.now() - dt).total_seconds()
            report["_age_seconds"] = age_seconds
            report["_age_display"] = _format_age(age_seconds)
            report["_fresh"] = age_seconds < 3600  # Fresh if < 1 hour
        except (ValueError, TypeError):
            report["_age_display"] = "unknown"
            report["_fresh"] = False
    else:
        report["_age_display"] = "unknown"
        report["_fresh"] = False

    # Classify overall divergence level
    thesis_j = report.get("thesis_overlap_jaccard", 0)
    position_j = report.get("position_overlap_jaccard", 0)
    if thesis_j > 0.7 and position_j > 0.6:
        report["_divergence_level"] = "low"
    elif thesis_j > 0.4 and position_j > 0.3:
        report["_divergence_level"] = "moderate"
    else:
        report["_divergence_level"] = "high"


def _format_age(seconds: float) -> str:
    """Format seconds into human-readable age string."""
    if seconds < 0:
        return "unknown"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"
