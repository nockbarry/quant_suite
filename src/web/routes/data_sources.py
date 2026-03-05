"""Data sources routes — freshness grid and manual refresh trigger.

Logic is implemented directly in the route since this operates on files
rather than database tables.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from src.web.services.task_manager import get_task_manager

router = APIRouter()


def _results_dir() -> Path:
    return Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))


def _get_data_sources() -> list[dict]:
    """Scan known data source directories and report freshness."""
    results = _results_dir()
    sources = []

    # Map of source name -> (directory/file, description)
    # Paths must match where collectors ACTUALLY write data
    source_map = {
        # Core state
        "state.json": ("live/state.json", "Unified live state"),

        # News (expanded_news writes here, fast_news writes to live/news_cache.json)
        "news": ("live/news", "Market news feeds (15+ RSS)"),
        "news_fast": ("live/news_cache.json", "Fast news with thesis matching"),

        # Social signals
        "social_wsb": ("social/wsb.db", "WSB/Reddit mentions"),
        "social_stocktwits": ("social/stocktwits_cache.json", "Stocktwits sentiment"),

        # Screens & signals
        "finviz_screens": ("scraped_data/finviz/screens_latest.json", "Finviz stock screens (8)"),

        # Alternative data
        "congressional": ("logs/congressional_collection_history.json", "Congressional trades"),
        "insider": ("logs/insider_collection_history.json", "Insider trading (Form 4)"),
        "geopolitical": ("live/geopolitical", "Geopolitical event tracking"),
        "legal": ("live/legal", "Legal/regulatory tracking"),
        "prediction_markets": ("live/research/prediction_markets", "Prediction markets"),

        # Market regime (read from state.json)
        "vix_structure": ("live/state.json", "VIX term structure"),
        "breadth": ("live/state.json", "Market breadth"),

        # Calendars (read from state.json)
        "earnings_calendar": ("live/state.json", "Earnings calendar"),
        "economic_calendar": ("live/state.json", "Economic releases"),
        "fda_calendar": ("live/state.json", "FDA PDUFA dates"),

        # Persistent stores
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
    hourly_sources = {"news", "news_fast", "fed_futures", "options_flow"}
    # Daily sources
    daily_sources = {"congressional", "insider", "earnings_calendar", "economic_calendar",
                     "fda_calendar", "ipo_calendar", "finviz_screens", "social_wsb",
                     "social_stocktwits", "geopolitical", "legal", "prediction_markets"}
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
            "breadcrumbs": [
                {"label": "Data Sources"},
            ],
        },
    )


_PERSISTENT_SOURCES = {"theses", "learnings", "knowledge", "decisions"}


@router.post("/{source}/refresh")
async def refresh_source(request: Request, source: str):
    """Trigger a real background refresh of a data source via task manager."""
    if source in _PERSISTENT_SOURCES:
        return HTMLResponse(
            '<span class="text-xs text-gray-500">Persistent source — no refresh needed</span>'
        )

    from src.web.routes.tasks import _dispatch_action
    try:
        task_id = _dispatch_action(f"collect_source:{source}")
    except ValueError:
        task_id = _dispatch_action(f"collect_source:{source}")

    task = get_task_manager().get_task(task_id)

    from src.web.routes.tasks import _render_task_status
    return HTMLResponse(_render_task_status(task))


@router.post("/refresh-all")
async def refresh_all(request: Request):
    """Trigger full data collection via task manager."""
    from src.web.routes.tasks import _dispatch_action, _render_task_status
    task_id = _dispatch_action("collect_data")
    task = get_task_manager().get_task(task_id)
    return HTMLResponse(_render_task_status(task))
