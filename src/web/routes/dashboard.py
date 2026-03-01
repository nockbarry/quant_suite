"""Dashboard routes — main landing page and activity feed."""

from fastapi import APIRouter, Request

from src.web.services import state_service

router = APIRouter()


@router.get("/")
async def index(request: Request):
    """Main dashboard: state overview, portfolio summary, recent events, autonomy status."""
    templates = request.app.state.templates

    state = state_service.get_live_state()
    portfolio = state_service.get_portfolio_summary(state)
    state_age = state_service.get_state_age_seconds()

    # Recent process events for activity feed
    from src.web.services import flow_service

    recent_events = flow_service.list_events(limit=20)

    # Autonomy status (latest check)
    from src.web.services import system_service

    autonomy_data = system_service.get_autonomy_status()
    latest_check = autonomy_data.get("recent_checks", [None])[0] if autonomy_data.get("recent_checks") else None

    # Recent documents for dashboard widget
    from src.web.services import document_service

    recent_docs, _ = document_service.list_documents(limit=8)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "dashboard",
            "state": state,
            "portfolio": portfolio,
            "state_age": state_age,
            "events": recent_events,
            "market": state.get("market", {}),
            "autonomy": latest_check,
            "recent_docs": recent_docs,
        },
    )


@router.get("/partials/activity-feed")
async def activity_feed_partial(request: Request):
    """HTMX partial: refreshable activity feed."""
    from src.web.services import flow_service

    events = flow_service.list_events(limit=20)
    html_parts = []
    for event in events:
        severity_class = "bg-blue-500"
        if event.get("severity") == "critical":
            severity_class = "bg-red-500"
        elif event.get("severity") == "warning":
            severity_class = "bg-yellow-500"
        ts = (event.get("timestamp") or "")[:16]
        html_parts.append(
            f'<div class="px-4 py-2 hover:bg-gray-800/30">'
            f'<div class="flex items-center gap-2">'
            f'<span class="w-2 h-2 rounded-full {severity_class}"></span>'
            f'<span class="text-xs text-gray-400 mono">{ts}</span>'
            f'</div>'
            f'<p class="text-sm text-gray-300 mt-0.5">{event.get("title", "")}</p>'
            f'</div>'
        )
    from starlette.responses import HTMLResponse
    return HTMLResponse("\n".join(html_parts) if html_parts else '<div class="px-4 py-8 text-center text-gray-600 text-sm">No recent activity</div>')
