"""Swarm routes — situation board, strategic context, sentinel status."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services import swarm_service

router = APIRouter()


@router.get("/")
async def swarm_index(request: Request):
    """Main swarm dashboard: situation board + strategic context + sentinel."""
    templates = request.app.state.templates

    board = swarm_service.get_situation_board()
    context = swarm_service.get_strategic_context()
    sentinel = swarm_service.get_sentinel_health()
    completions = swarm_service.get_recent_completions()

    return templates.TemplateResponse(
        request,
        "swarm/index.html",
        {
            "active_page": "swarm",
            "board": board,
            "context": context,
            "sentinel": sentinel,
            "completions": completions,
        },
    )


@router.get("/board")
async def swarm_board_partial(request: Request):
    """HTMX partial: situation board (auto-refreshes)."""
    templates = request.app.state.templates
    board = swarm_service.get_situation_board()
    return templates.TemplateResponse(
        request,
        "swarm/board_partial.html",
        {"board": board},
    )
