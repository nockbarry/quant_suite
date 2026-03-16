"""Risk routes — stress test results and portfolio risk dashboard."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services import risk_service

router = APIRouter()


@router.get("/")
async def risk_index(request: Request):
    """Main risk dashboard: stress test results, VaR, concentration."""
    templates = request.app.state.templates

    report = risk_service.get_latest_report()
    history = risk_service.get_report_history(limit=5)

    return templates.TemplateResponse(
        request,
        "risk/index.html",
        {
            "active_page": "risk",
            "report": report,
            "history": history,
        },
    )
