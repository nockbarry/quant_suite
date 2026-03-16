"""Meta-observer routes — cross-instance analysis dashboard."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services import meta_service

router = APIRouter()


@router.get("/")
async def meta_index(request: Request):
    """Meta-observer dashboard — cross-instance analysis."""
    templates = request.app.state.templates

    data = meta_service.get_meta_dashboard_data()

    return templates.TemplateResponse(
        request,
        "meta/index.html",
        {
            "active_page": "meta",
            **data,
        },
    )


@router.get("/refresh")
async def meta_refresh(request: Request):
    """Run a fresh meta-observer analysis and redirect to dashboard."""
    from starlette.responses import RedirectResponse

    meta_service.run_fresh_analysis()
    return RedirectResponse(url="/meta", status_code=303)
