"""Bug monitor dashboard."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/")
async def bugs_index(request: Request):
    """Bug detection and tracking dashboard."""
    from src.web.services.bug_service import get_bug_dashboard_data
    templates = request.app.state.templates
    data = get_bug_dashboard_data()
    return templates.TemplateResponse(request, "bugs/index.html", {"active_page": "bugs", **data})
