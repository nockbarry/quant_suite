"""Theses routes — investment thesis management."""

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.services import thesis_service

router = APIRouter()


@router.get("/")
async def thesis_list(request: Request):
    """List all theses as a card grid."""
    templates = request.app.state.templates

    filter_status = request.query_params.get("status", "all")
    theses = thesis_service.list_theses()

    return templates.TemplateResponse(
        request,
        "theses/index.html",
        {
            "active_page": "theses",
            "theses": theses,
            "filter_status": filter_status,
        },
    )


@router.get("/new")
async def thesis_new(request: Request):
    """Form for creating a new thesis."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "theses/form.html",
        {
            "active_page": "theses",
            "thesis": None,
            "breadcrumbs": [
                {"label": "Theses", "url": "/theses"},
                {"label": "New Thesis"},
            ],
        },
    )


@router.get("/{thesis_id}/edit")
async def thesis_edit(request: Request, thesis_id: str):
    """Form for editing an existing thesis."""
    templates = request.app.state.templates
    thesis = thesis_service.get_thesis(thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found")
    return templates.TemplateResponse(
        request,
        "theses/form.html",
        {
            "active_page": "theses",
            "thesis": thesis,
            "breadcrumbs": [
                {"label": "Theses", "url": "/theses"},
                {"label": thesis.get("name", thesis_id) if isinstance(thesis, dict) else getattr(thesis, "name", thesis_id), "url": f"/theses/{thesis_id}"},
                {"label": "Edit"},
            ],
        },
    )


@router.get("/{thesis_id}")
async def thesis_detail(request: Request, thesis_id: str):
    """Thesis detail with signposts, linked decisions, and performance."""
    templates = request.app.state.templates

    thesis = thesis_service.get_thesis(thesis_id)
    if thesis is None:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found")

    decisions = thesis_service.get_thesis_decisions(thesis_id)
    performance = thesis_service.get_thesis_performance(thesis_id)

    from src.web.services import document_service
    related_docs = document_service.get_documents_for_thesis(thesis_id)

    # Linked predictions
    try:
        from src.web.services import intelligence_service
        all_preds = intelligence_service.list_predictions(limit=50)
        thesis_predictions = [p for p in all_preds if p.get("thesis_id") == thesis_id]
    except Exception:
        thesis_predictions = []

    # Position P&L and current prices from state.json
    position_pnl = {}
    position_prices = {}
    try:
        import json
        from src.core.paths import paths
        state_file = paths.live_state
        if state_file.exists():
            with open(state_file) as f:
                state_data = json.load(f)
            positions_data = state_data.get("positions", []) or state_data.get("portfolio", {}).get("positions", []) or []
            for pos in positions_data:
                sym = pos.get("symbol", "")
                if sym:
                    position_pnl[sym] = pos.get("unrealized_pnl_pct", 0)
                    position_prices[sym] = pos.get("current_price", 0)
    except Exception:
        pass

    # Price target progress
    price_target_progress = {}
    thesis_dict = thesis if isinstance(thesis, dict) else thesis
    pts = thesis_dict.get("price_targets", {}) if isinstance(thesis_dict, dict) else {}
    for sym, pt in pts.items():
        current_price = position_prices.get(sym, 0)
        if current_price and pt.get("base_target"):
            entry = pt.get("entry_price", 0)
            base = pt["base_target"]
            bull = pt.get("bull_target", base)
            bear = pt.get("bear_target", entry)
            progress = ((current_price - entry) / (base - entry) * 100) if base != entry else 0
            price_target_progress[sym] = {
                **pt,
                "current_price": current_price,
                "progress_pct": round(max(-100, min(200, progress)), 1),
            }

    return templates.TemplateResponse(
        request,
        "theses/detail.html",
        {
            "active_page": "theses",
            "thesis": thesis,
            "decisions": decisions,
            "performance": performance,
            "related_docs": related_docs,
            "thesis_predictions": thesis_predictions,
            "position_pnl": position_pnl,
            "price_target_progress": price_target_progress,
            "breadcrumbs": [
                {"label": "Theses", "url": "/theses"},
                {"label": thesis.get("name", thesis_id) if isinstance(thesis, dict) else getattr(thesis, "name", thesis_id)},
            ],
        },
    )


@router.post("/")
async def create_thesis(
    request: Request,
    name: str = Form(...),
    summary: str = Form(""),
    conviction: float = Form(50.0),
    bull_case: str = Form(""),
    bear_case: str = Form(""),
    positions: str = Form(""),
):
    """Create a new thesis from form submission."""
    # Parse comma-separated positions
    position_list = [p.strip().upper() for p in positions.split(",") if p.strip()]

    data = {
        "name": name,
        "summary": summary,
        "conviction": conviction,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "positions": position_list,
    }
    thesis = thesis_service.create_thesis(data)
    return RedirectResponse(url=f"/theses/{thesis['id']}", status_code=303)


@router.put("/{thesis_id}")
async def update_thesis(request: Request, thesis_id: str):
    """Update a thesis from form data."""
    form = await request.form()
    data = {}
    for k, v in form.items():
        if k == "positions":
            data[k] = [p.strip().upper() for p in v.split(",") if p.strip()]
        elif k == "conviction":
            data[k] = float(v)
        else:
            data[k] = v

    updated = thesis_service.update_thesis(thesis_id, data)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found")

    return RedirectResponse(url=f"/theses/{thesis_id}", status_code=303)


@router.post("/{thesis_id}/conviction")
@router.put("/{thesis_id}/conviction")
async def update_conviction(
    request: Request,
    thesis_id: str,
    conviction: float = Form(...),
    reason: str = Form(""),
):
    """HTMX endpoint: update conviction level and return updated badge."""
    updated = thesis_service.update_conviction(thesis_id, conviction, reason)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found")

    conv = updated.get("conviction", conviction) if isinstance(updated, dict) else getattr(updated, "conviction", conviction)

    if conv >= 70:
        color = "text-emerald-400"
    elif conv >= 40:
        color = "text-yellow-400"
    else:
        color = "text-red-400"

    if conv < 30:
        gradient = "#ef4444, #f97316"
    elif conv < 60:
        gradient = "#f97316, #eab308"
    elif conv < 80:
        gradient = "#eab308, #22c55e"
    else:
        gradient = "#22c55e, #10b981"

    html = f"""
    <div class="flex items-center justify-between mb-2">
        <h2 class="text-sm font-semibold text-gray-300">Conviction</h2>
        <span class="mono text-lg font-bold {color}">{conv:.0f}%</span>
    </div>
    <div class="w-full bg-gray-800 rounded-full h-1.5 mb-3">
        <div class="h-1.5 rounded-full transition-all duration-500"
             style="width: {conv}%; background: linear-gradient(90deg, {gradient});">
        </div>
    </div>
    """
    return HTMLResponse(content=html)


@router.post("/{thesis_id}/notes")
async def add_note(
    request: Request,
    thesis_id: str,
    note: str = Form(...),
):
    """HTMX endpoint: add a note to a thesis."""
    updated = thesis_service.add_note(thesis_id, note)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Thesis '{thesis_id}' not found")

    html = f'<p class="text-xs text-gray-400 border-l-2 border-gray-700 pl-3 py-1">{note}</p>'
    return HTMLResponse(content=html)
