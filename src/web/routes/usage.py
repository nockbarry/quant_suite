"""Usage monitoring routes — Claude Code Max plan usage dashboard."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.monitoring.usage_monitor import get_usage_summary, get_session_breakdown, format_tokens

router = APIRouter()


@router.get("/")
async def usage_dashboard(request: Request):
    """Main usage dashboard."""
    templates = request.app.state.templates
    summary = get_usage_summary(days=30)
    sessions = get_session_breakdown()

    # Pre-serialize days for Chart.js (Jinja can't call methods on dataclasses)
    days_json = [d.to_dict() for d in summary.days]

    return templates.TemplateResponse(
        request,
        "usage/dashboard.html",
        {
            "active_page": "usage",
            "summary": summary,
            "sessions": sessions,
            "days_json": days_json,
            "format_tokens": format_tokens,
        },
    )


@router.get("/api/stats")
async def usage_api(request: Request):
    """JSON API for usage stats."""
    days = int(request.query_params.get("days", 30))
    summary = get_usage_summary(days=days)
    return JSONResponse(summary.to_dict())
