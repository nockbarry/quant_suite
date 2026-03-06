"""Review service — reads EOD reviews, internal reviews, and briefings."""

import json
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path.home() / "quant_results"
EOD_DIR = RESULTS_DIR / "eod_reviews"
REVIEWS_DIR = RESULTS_DIR / "reviews"
BRIEFINGS_DIR = RESULTS_DIR / "briefings"


def get_eod_reviews(limit: int = 20) -> list[dict]:
    """Get recent EOD review summaries, newest first."""
    if not EOD_DIR.exists():
        return []
    files = sorted(EOD_DIR.glob("review_*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            data["_filename"] = f.name
            data["_date"] = data.get("date", f.stem.replace("review_", ""))
            results.append(data)
        except Exception:
            continue
    return results


def get_eod_review(date: str) -> dict | None:
    """Get a specific EOD review by date (YYYYMMDD or YYYY-MM-DD)."""
    date_clean = date.replace("-", "")
    path = EOD_DIR / f"review_{date_clean}.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        data["_date"] = data.get("date", date_clean)
        return data
    except Exception:
        return None


def get_internal_reviews(limit: int = 10) -> list[dict]:
    """Get recent internal review reports."""
    if not REVIEWS_DIR.exists():
        return []
    files = sorted(REVIEWS_DIR.glob("internal_review_*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            data["_filename"] = f.name
            results.append(data)
        except Exception:
            continue
    return results


def get_briefings(limit: int = 10) -> list[dict]:
    """Get recent briefing summaries (JSON only), newest first."""
    if not BRIEFINGS_DIR.exists():
        return []
    files = sorted(BRIEFINGS_DIR.glob("briefing_*.json"), reverse=True)[:limit]
    results = []
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            data["_filename"] = f.name
            data["_date"] = data.get("date", f.stem.replace("briefing_", ""))
            results.append(data)
        except Exception:
            continue
    return results


def get_briefing(date: str) -> dict | None:
    """Get a specific briefing by date."""
    date_clean = date.replace("-", "")
    # Try both formats
    for pattern in [f"briefing_{date_clean}.json", f"briefing_{date[:10]}.json"]:
        path = BRIEFINGS_DIR / pattern
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                continue
    return None
