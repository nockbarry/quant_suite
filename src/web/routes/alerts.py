"""Cross-reference alerts dashboard."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def alerts_index(request: Request):
    """Cross-reference alerts dashboard."""
    from src.web.services.alerts_service import get_alerts_dashboard_data
    templates = request.app.state.templates
    data = get_alerts_dashboard_data()
    return templates.TemplateResponse(request, "alerts/index.html", {"active_page": "alerts", **data})
