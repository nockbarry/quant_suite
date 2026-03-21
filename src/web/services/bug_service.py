"""Bug monitor dashboard data service."""
import json
from src.core.paths import paths


def get_bug_dashboard_data() -> dict:
    """Load bug report data for the web dashboard."""
    report_file = paths.base / "logs" / "bug_reports.json"

    bugs = []
    summary = {
        "total": 0,
        "crashes": 0,
        "errors": 0,
        "warnings": 0,
        "silent_failures": 0,
        "auto_fixable": 0,
        "recurring": 0,
        "top_errors": [],
    }
    last_scan = None

    if report_file.exists():
        try:
            with open(report_file) as f:
                data = json.load(f)
            bugs = data.get("bugs", [])
            summary = data.get("summary", summary)
            last_scan = data.get("timestamp")
        except (json.JSONDecodeError, OSError):
            pass

    # Separate by severity for display
    crashes = [b for b in bugs if b.get("severity") == "crash"]
    errors = [b for b in bugs if b.get("severity") == "error"]
    warnings = [b for b in bugs if b.get("severity") == "warning"]
    silent_failures = [b for b in bugs if b.get("severity") == "silent_failure"]
    auto_fixable = [b for b in bugs if b.get("auto_fixable") and not b.get("fix_applied")]
    recurring = [b for b in bugs if b.get("occurrence_count", 0) >= 3]

    return {
        "bugs": bugs,
        "crashes": crashes,
        "errors": errors,
        "warnings": warnings,
        "silent_failures": silent_failures,
        "auto_fixable": auto_fixable,
        "recurring": recurring,
        "summary": summary,
        "last_scan": last_scan,
    }
