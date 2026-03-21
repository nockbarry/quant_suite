"""Autonomous upgrade history dashboard."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def upgrades_index(request: Request):
    """Show upgrade history and pending proposals."""
    from src.web.services.upgrade_service import get_upgrade_dashboard_data
    templates = request.app.state.templates
    data = get_upgrade_dashboard_data()
    return templates.TemplateResponse(request, "upgrades/index.html", {"active_page": "upgrades", **data})
