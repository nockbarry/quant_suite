"""Data sources routes — freshness grid and manual refresh trigger.

Logic is implemented directly in the route since this operates on files
rather than database tables.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _get_data_sources() -> list[dict]:
    """Scan known data source directories and report freshness."""
    results = _results_dir()
    sources = []

    # Map of source name -> (directory/file, description)
    source_map = {
        "state.json": ("live/state.json", "Unified live state"),
        "congressional": ("live/research/congressional", "Congressional trades"),
        "insider": ("live/research/insider", "Insider trading (Form 4)"),
        "options_flow": ("live/research/options_flow", "Options flow data"),
        "social_wsb": ("live/research/social/wsb", "WSB mentions"),
        "social_stocktwits": ("live/research/social/stocktwits", "Stocktwits sentiment"),
        "news": ("live/research/news", "Market news feeds"),
        "earnings_calendar": ("live/research/earnings", "Earnings calendar"),
        "economic_calendar": ("live/research/economic", "Economic releases"),
        "fda_calendar": ("live/research/fda", "FDA PDUFA dates"),
        "ipo_calendar": ("live/research/ipo", "IPO calendar"),
        "vix_structure": ("live/research/vix", "VIX term structure"),
        "finviz_screens": ("live/research/finviz", "Finviz stock screens"),
        "aaii_sentiment": ("live/research/sentiment/aaii", "AAII investor survey"),
        "fed_futures": ("live/research/fed", "Fed funds futures"),
        "breadth": ("live/research/breadth", "Market breadth"),
        "theses": ("theses", "Investment theses"),
        "learnings": ("learnings", "Trade learnings"),
        "knowledge": ("knowledge", "Company/sector knowledge"),
        "decisions": ("decisions", "Trading decisions"),
    }

    now = datetime.utcnow()

    for name, (rel_path, description) in source_map.items():
        full_path = results / rel_path
        source_info = {
            "name": name,
            "description": description,
            "path": str(full_path),
            "exists": False,
            "last_updated": None,
            "age_seconds": None,
            "age_human": "N/A",
            "status": "missing",
            "file_count": 0,
        }

        if full_path.exists():
            source_info["exists"] = True

            if full_path.is_file():
                mtime = datetime.utcfromtimestamp(full_path.stat().st_mtime)
                source_info["last_updated"] = mtime.isoformat()
                age = int((now - mtime).total_seconds())
                source_info["age_seconds"] = age
                source_info["age_human"] = _human_age(age)
                source_info["file_count"] = 1
                source_info["status"] = _freshness_status(name, age)
            elif full_path.is_dir():
                files = list(full_path.glob("**/*"))
                data_files = [f for f in files if f.is_file() and not f.name.startswith(".")]
                source_info["file_count"] = len(data_files)

                if data_files:
                    newest = max(data_files, key=lambda f: f.stat().st_mtime)
                    mtime = datetime.utcfromtimestamp(newest.stat().st_mtime)
                    source_info["last_updated"] = mtime.isoformat()
                    age = int((now - mtime).total_seconds())
                    source_info["age_seconds"] = age
                    source_info["age_human"] = _human_age(age)
                    source_info["status"] = _freshness_status(name, age)
                else:
                    source_info["status"] = "empty"

        sources.append(source_info)

    return sources


def _human_age(seconds: int) -> str:
    """Convert seconds to human-readable age."""
    if seconds < 60:
        return f"{seconds}s ago"
    elif seconds < 3600:
        return f"{seconds // 60}m ago"
    elif seconds < 86400:
        return f"{seconds // 3600}h ago"
    else:
        return f"{seconds // 86400}d ago"


def _freshness_status(source_name: str, age_seconds: int) -> str:
    """Determine freshness status based on source type and age."""
    # Real-time sources (should update every few minutes)
    realtime_sources = {"state.json", "breadth", "vix_structure"}
    # Hourly sources
    hourly_sources = {"news", "fed_futures", "options_flow"}
    # Daily sources
    daily_sources = {"congressional", "insider", "earnings_calendar", "economic_calendar",
                     "fda_calendar", "ipo_calendar", "finviz_screens", "social_wsb",
                     "social_stocktwits"}
    # Persistent stores (always OK)
    persistent_sources = {"theses", "learnings", "knowledge", "decisions"}

    if source_name in persistent_sources:
        return "ok"

    if source_name in realtime_sources:
        if age_seconds < 600:      # 10 min
            return "fresh"
        elif age_seconds < 1800:   # 30 min
            return "ok"
        elif age_seconds < 3600:   # 1 hr
            return "stale"
        else:
            return "critical"
    elif source_name in hourly_sources:
        if age_seconds < 3600:     # 1 hr
            return "fresh"
        elif age_seconds < 7200:   # 2 hr
            return "ok"
        elif age_seconds < 14400:  # 4 hr
            return "stale"
        else:
            return "critical"
    elif source_name in daily_sources:
        if age_seconds < 86400:    # 1 day
            return "fresh"
        elif age_seconds < 172800: # 2 days
            return "ok"
        elif age_seconds < 345600: # 4 days
            return "stale"
        else:
            return "critical"
    else:
        # Default thresholds
        if age_seconds < 3600:
            return "fresh"
        elif age_seconds < 86400:
            return "ok"
        else:
            return "stale"


@router.get("/")
async def data_source_grid(request: Request):
    """Data source grid with freshness indicators."""
    templates = request.app.state.templates

    sources = _get_data_sources()

    # Summary counts
    status_counts = {}
    for s in sources:
        st = s["status"]
        status_counts[st] = status_counts.get(st, 0) + 1

    return templates.TemplateResponse(
        request,
        "data_sources/index.html",
        {
            "active_page": "data",
            "sources": sources,
            "status_counts": status_counts,
        },
    )


@router.post("/{source}/refresh")
async def refresh_source(request: Request, source: str):
    """Trigger a manual refresh of a data source.

    This writes a refresh request file that the collection daemon picks up.
    Returns JSON status for HTMX swap.
    """
    results = _results_dir()
    refresh_dir = results / "live" / "refresh_requests"
    refresh_dir.mkdir(parents=True, exist_ok=True)

    request_file = refresh_dir / f"{source}.json"
    request_data = {
        "source": source,
        "requested_at": datetime.utcnow().isoformat(),
        "requested_by": "web_dashboard",
    }
    request_file.write_text(json.dumps(request_data, indent=2))

    return JSONResponse(
        content={
            "status": "queued",
            "source": source,
            "message": f"Refresh request queued for '{source}'",
        }
    )
