"""Learnings routes — trade learnings feed and management."""

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.services import learning_service

router = APIRouter()


@router.get("/")
async def learning_list(request: Request):
    """Learning feed with optional filters."""
    templates = request.app.state.templates

    # Parse query filters
    outcome = request.query_params.get("outcome")
    symbol = request.query_params.get("symbol")
    pattern = request.query_params.get("pattern")
    limit = int(request.query_params.get("limit", 50))

    learnings = learning_service.list_learnings(
        outcome=outcome,
        symbol=symbol,
        pattern_name=pattern,
        limit=limit,
    )

    stats = learning_service.get_learning_stats()
    outcomes = stats.get("outcomes", {})
    wins = outcomes.get("win", 0) + outcomes.get("profit", 0)
    losses = outcomes.get("loss", 0)
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    stats_ctx = {
        "total": stats.get("total", 0),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "avg_pnl": stats.get("avg_pnl_pct", 0),
    }

    return templates.TemplateResponse(
        request,
        "learnings/index.html",
        {
            "active_page": "learnings",
            "learnings": learnings,
            "stats": stats_ctx,
            "filters": {
                "outcome": outcome,
                "symbol": symbol,
                "pattern": pattern,
            },
        },
    )


@router.get("/stats")
async def learning_stats(request: Request):
    """HTMX partial: learning statistics panel."""
    stats = learning_service.get_learning_stats()

    total = stats.get("total", 0)
    outcomes = stats.get("outcomes", {})
    wins = outcomes.get("win", 0) + outcomes.get("profit", 0)
    losses = outcomes.get("loss", 0)
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    avg_pnl = stats.get("avg_pnl_pct", 0)

    win_rate_color = "text-profit" if win_rate >= 50 else "text-loss"
    avg_pnl_color = "text-profit" if avg_pnl >= 0 else "text-loss"

    html = f"""
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Total Learnings</p>
        <p class="text-lg font-bold mono text-gray-200">{total}</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Wins</p>
        <p class="text-lg font-bold mono text-profit">{wins}</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Losses</p>
        <p class="text-lg font-bold mono text-loss">{losses}</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Win Rate</p>
        <p class="text-lg font-bold mono {win_rate_color}">{win_rate:.0f}%</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Avg P&amp;L</p>
        <p class="text-lg font-bold mono {avg_pnl_color}">{avg_pnl:+.1f}%</p>
    </div>
    """
    return HTMLResponse(content=html)


@router.get("/{learning_id}")
async def learning_detail(request: Request, learning_id: str):
    """Learning detail page."""
    templates = request.app.state.templates

    learning = learning_service.get_learning(learning_id)
    if learning is None:
        raise HTTPException(status_code=404, detail=f"Learning '{learning_id}' not found")

    return templates.TemplateResponse(
        request,
        "learnings/detail.html",
        {
            "active_page": "learnings",
            "learning": learning,
        },
    )


@router.post("/")
async def create_learning(
    request: Request,
    symbol: str = Form(...),
    action: str = Form(...),
    outcome: str = Form(...),
    pnl_pct: float = Form(0.0),
    what_happened: str = Form(""),
    what_i_learned: str = Form(""),
    how_this_changes_approach: str = Form(""),
    pattern_name: str = Form(""),
    tags: str = Form(""),
    thesis_id: str = Form(""),
    decision_id: str = Form(""),
):
    """Create a new learning from form submission."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    data = {
        "symbol": symbol.upper(),
        "action": action.upper(),
        "outcome": outcome,
        "pnl_pct": pnl_pct,
        "what_happened": what_happened,
        "what_i_learned": what_i_learned,
        "how_this_changes_approach": how_this_changes_approach,
        "pattern_name": pattern_name or None,
        "tags": tag_list,
        "thesis_id": thesis_id or None,
        "decision_id": decision_id or None,
    }
    learning = learning_service.create_learning(data)
    return RedirectResponse(url=f"/learnings/{learning['id']}", status_code=303)
