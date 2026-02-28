"""Theses routes — investment thesis management."""

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.services import thesis_service

router = APIRouter()


@router.get("/")
async def thesis_list(request: Request):
    """List all theses as a card grid."""
    templates = request.app.state.templates

    theses = thesis_service.list_theses()

    return templates.TemplateResponse(
        request,
        "theses/index.html",
        {
            "active_page": "theses",
            "theses": theses,
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

    return templates.TemplateResponse(
        request,
        "theses/detail.html",
        {
            "active_page": "theses",
            "thesis": thesis,
            "decisions": decisions,
            "performance": performance,
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
