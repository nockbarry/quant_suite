"""Movers routes — market mover analysis dashboard."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services import mover_service

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def movers_index(request: Request):
    """Market movers dashboard: gainers, losers, volume spikes, top context."""
    templates = request.app.state.templates

    scan = mover_service.get_latest_scan()
    history = mover_service.get_scan_history()

    return templates.TemplateResponse(
        request,
        "movers/index.html",
        {
            "active_page": "movers",
            "scan": scan,
            "history": history,
        },
    )


@router.get("/{symbol}", response_class=HTMLResponse)
async def mover_detail(request: Request, symbol: str):
    """Detail view for a single market mover."""
    templates = request.app.state.templates
    mover = mover_service.get_mover_detail(symbol.upper())
    scan = mover_service.get_latest_scan()

    return templates.TemplateResponse(
        request,
        "movers/detail.html",
        {
            "active_page": "movers",
            "mover": mover,
            "symbol": symbol.upper(),
            "scan_time": scan.get("timestamp", ""),
        },
    )
