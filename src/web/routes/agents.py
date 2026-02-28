"""Agents routes — agent run list, detail, and aggregate metrics."""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.web.services import agent_service

router = APIRouter()


@router.get("/")
async def agent_list(request: Request):
    """Agent run list with metrics panel."""
    templates = request.app.state.templates

    # Parse query filters
    agent_type = request.query_params.get("agent_type")
    status = request.query_params.get("status")
    limit = int(request.query_params.get("limit", 50))

    runs = agent_service.list_runs(
        agent_type=agent_type,
        status=status,
        limit=limit,
    )
    metrics = agent_service.get_aggregate_metrics()

    return templates.TemplateResponse(
        request,
        "agents/index.html",
        {
            "active_page": "agents",
            "runs": runs,
            "metrics": metrics,
            "filters": {
                "agent_type": agent_type,
                "status": status,
            },
        },
    )


@router.get("/metrics")
async def agent_metrics_partial(request: Request):
    """HTMX partial: aggregate agent metrics."""
    metrics = agent_service.get_aggregate_metrics()

    def _get(key, default=0):
        if isinstance(metrics, dict):
            return metrics.get(key, default)
        return getattr(metrics, key, default)

    total_runs = _get("total_runs", 0)
    total_cost = _get("total_cost", 0)
    avg_duration = _get("avg_duration_sec", 0)
    signals_gen = _get("signals_generated", 0)
    decisions_inf = _get("decisions_influenced", 0)

    html = f"""
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Total Runs</p>
        <p class="text-lg font-bold mono text-gray-200">{total_runs}</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Total Cost</p>
        <p class="text-lg font-bold mono text-gray-200">${total_cost:.2f}</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Avg Duration</p>
        <p class="text-lg font-bold mono text-gray-200">{avg_duration:.0f}s</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Signals Generated</p>
        <p class="text-lg font-bold mono text-emerald-400">{signals_gen}</p>
    </div>
    <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
        <p class="text-[10px] text-gray-500 uppercase">Decisions Influenced</p>
        <p class="text-lg font-bold mono text-blue-400">{decisions_inf}</p>
    </div>
    """
    return HTMLResponse(content=html)


@router.get("/{run_id}")
async def agent_detail(request: Request, run_id: str):
    """Agent run detail with findings and child runs."""
    templates = request.app.state.templates

    run = agent_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Agent run '{run_id}' not found")

    children = agent_service.get_child_runs(run_id)
    events = agent_service.get_run_events(run_id)

    return templates.TemplateResponse(
        request,
        "agents/detail.html",
        {
            "active_page": "agents",
            "run": run,
            "children": children,
            "events": events,
        },
    )
