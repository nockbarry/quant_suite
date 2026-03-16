"""War/geopolitical monitoring dashboard."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def war_index(request: Request):
    """War dashboard -- real-time geopolitical monitoring."""
    from src.web.services.war_service import get_war_dashboard_data

    templates = request.app.state.templates
    data = get_war_dashboard_data()
    return templates.TemplateResponse(
        request, "war/index.html", {"active_page": "war", **data}
    )
