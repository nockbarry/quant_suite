"""Sessions routes — autonomous session dashboard, timeline, and news feed."""

from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services import session_service

router = APIRouter()


@router.get("/")
async def sessions_index(request: Request):
    """Main sessions dashboard: live status + timeline + news."""
    templates = request.app.state.templates

    live_status = session_service.get_live_status()
    todays_sessions = session_service.get_todays_sessions()
    stats = session_service.get_session_stats(days=7)

    return templates.TemplateResponse(
        request,
        "sessions/index.html",
        {
            "active_page": "sessions",
            "live_status": live_status,
            "todays_sessions": todays_sessions,
            "stats": stats,
            "today": datetime.now().strftime("%Y-%m-%d"),
        },
    )


@router.get("/timeline")
async def sessions_timeline(request: Request):
    """HTMX partial: today's event timeline (auto-refreshes)."""
    templates = request.app.state.templates

    date_str = request.query_params.get("date")
    events = session_service.get_day_timeline(date_str)

    return templates.TemplateResponse(
        request,
        "sessions/timeline_partial.html",
        {
            "events": events,
            "date": date_str or datetime.now().strftime("%Y-%m-%d"),
        },
    )


@router.get("/news")
async def sessions_news(request: Request):
    """HTMX partial: enriched news feed with thesis links."""
    templates = request.app.state.templates

    hours = int(request.query_params.get("hours", 24))
    news = session_service.get_news_matches(hours=hours)

    return templates.TemplateResponse(
        request,
        "sessions/news_partial.html",
        {"news": news},
    )


@router.get("/{date}")
async def session_day_detail(request: Request, date: str):
    """Full day detail view with all autonomous events."""
    templates = request.app.state.templates

    events = session_service.get_day_timeline(date)
    stats = session_service.get_session_stats(days=1)

    # Group events by session type
    grouped: dict[str, list] = {}
    for evt in events:
        source = evt.get("source", "unknown")
        session_type = source.replace("scheduler:", "") if source.startswith("scheduler:") else source
        grouped.setdefault(session_type, []).append(evt)

    return templates.TemplateResponse(
        request,
        "sessions/day_detail.html",
        {
            "active_page": "sessions",
            "date": date,
            "events": events,
            "grouped": grouped,
            "stats": stats,
        },
    )
