"""Risk service — reads stress test reports for the web dashboard."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)

REPORT_DIR = paths.risk_reports


def get_latest_report() -> dict:
    """Load the most recent stress test report.

    Checks for stress_test_latest.json first (written by run_full_report),
    then falls back to the most recently modified file in risk_reports/.
    """
    # Try latest symlink first
    latest_path = REPORT_DIR / "stress_test_latest.json"
    if latest_path.exists():
        try:
            with open(latest_path) as f:
                report = json.load(f)
            report["_source"] = str(latest_path)
            _enrich_report(report)
            return report
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to read latest report: {e}")

    # Fallback: find most recent report file
    if REPORT_DIR.exists():
        files = sorted(
            REPORT_DIR.glob("stress_test_2*.json"),
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

    return {"missing": True, "message": "No stress test reports found. Run: PYTHONPATH=. python scripts/run_stress_test.py"}


def get_report_history(limit: int = 10) -> list:
    """Load recent stress test reports (summary only)."""
    if not REPORT_DIR.exists():
        return []

    files = sorted(
        REPORT_DIR.glob("stress_test_2*.json"),
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
                "var_95_pct": report.get("var_95_pct", 0),
                "concentration_risk_score": report.get("concentration_risk_score", 0),
                "position_count": report.get("position_count", 0),
                "filename": f.name,
            })
        except (json.JSONDecodeError, ValueError):
            continue

    return results


def _enrich_report(report: dict) -> None:
    """Add computed display fields to a report."""
    # Compute age
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

    # Classify overall risk level
    var95 = report.get("var_95_pct", 0)
    conc = report.get("concentration_risk_score", 0)
    if var95 > 4 or conc > 0.4:
        report["_risk_level"] = "high"
    elif var95 > 2.5 or conc > 0.25:
        report["_risk_level"] = "moderate"
    else:
        report["_risk_level"] = "low"

    # Worst scenario
    scenarios = report.get("scenario_results", [])
    if scenarios:
        worst = min(scenarios, key=lambda s: s.get("portfolio_impact_pct", 0))
        best = max(scenarios, key=lambda s: s.get("portfolio_impact_pct", 0))
        report["_worst_scenario"] = worst
        report["_best_scenario"] = best


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
