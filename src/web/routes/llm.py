"""LLM routes — interaction log and cost analysis."""

import html as html_mod

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.web.services import llm_service

router = APIRouter()


@router.get("/")
async def llm_list(request: Request):
    """LLM interaction list with cost summary."""
    templates = request.app.state.templates

    # Parse query filters
    trigger_type = request.query_params.get("trigger_type")
    model = request.query_params.get("model")
    limit = int(request.query_params.get("limit", 50))

    interactions = llm_service.list_interactions(
        trigger_type=trigger_type,
        model=model,
        limit=limit,
    )
    cost_summary = llm_service.get_cost_summary()

    return templates.TemplateResponse(
        request,
        "llm/index.html",
        {
            "active_page": "llm",
            "interactions": interactions,
            "cost_summary": cost_summary,
            "filters": {
                "trigger_type": trigger_type,
                "model": model,
            },
        },
    )


@router.get("/costs")
async def llm_costs_partial(request: Request):
    """HTMX partial: cost analysis breakdown."""
    cost_summary = llm_service.get_cost_summary()
    cost_by_model = llm_service.get_cost_by_model()
    cost_by_trigger = llm_service.get_cost_by_trigger()

    def _get(obj, key, default=0):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    total_cost = _get(cost_summary, "total_cost", 0)
    total_tokens = _get(cost_summary, "total_tokens", 0)
    total_calls = _get(cost_summary, "total_calls", 0)
    avg_cost = _get(cost_summary, "avg_cost_per_call", 0)

    # Build model breakdown rows
    model_rows = []
    if isinstance(cost_by_model, dict):
        items = cost_by_model.items()
    elif isinstance(cost_by_model, list):
        items = [((_get(m, "model", "unknown")), m) for m in cost_by_model]
    else:
        items = []

    for model_name, data in items:
        m_cost = _get(data, "cost", _get(data, "total_cost", 0))
        m_calls = _get(data, "calls", _get(data, "total_calls", 0))
        model_rows.append(
            f'<tr class="border-b border-gray-800/50">'
            f'<td class="px-3 py-2 text-gray-300 mono text-xs">{html_mod.escape(str(model_name))}</td>'
            f'<td class="px-3 py-2 text-right mono text-gray-400">{m_calls}</td>'
            f'<td class="px-3 py-2 text-right mono text-gray-400">${m_cost:.4f}</td>'
            f'</tr>'
        )

    model_table = "".join(model_rows) if model_rows else '<tr><td colspan="3" class="px-3 py-4 text-center text-gray-600 text-xs">No model data</td></tr>'

    # Build trigger breakdown rows
    trigger_rows = []
    if isinstance(cost_by_trigger, dict):
        t_items = cost_by_trigger.items()
    elif isinstance(cost_by_trigger, list):
        t_items = [(_get(t, "trigger", "unknown"), t) for t in cost_by_trigger]
    else:
        t_items = []

    for trigger_name, data in t_items:
        t_cost = _get(data, "cost", _get(data, "total_cost", 0))
        t_calls = _get(data, "calls", _get(data, "total_calls", 0))
        trigger_rows.append(
            f'<tr class="border-b border-gray-800/50">'
            f'<td class="px-3 py-2 text-gray-300 text-xs">{html_mod.escape(str(trigger_name))}</td>'
            f'<td class="px-3 py-2 text-right mono text-gray-400">{t_calls}</td>'
            f'<td class="px-3 py-2 text-right mono text-gray-400">${t_cost:.4f}</td>'
            f'</tr>'
        )

    trigger_table = "".join(trigger_rows) if trigger_rows else '<tr><td colspan="3" class="px-3 py-4 text-center text-gray-600 text-xs">No trigger data</td></tr>'

    html = f"""
    <div class="space-y-4">
        <!-- Summary Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <p class="text-[10px] text-gray-500 uppercase">Total Cost</p>
                <p class="text-lg font-bold mono text-gray-200">${total_cost:.4f}</p>
            </div>
            <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <p class="text-[10px] text-gray-500 uppercase">Total Tokens</p>
                <p class="text-lg font-bold mono text-gray-200">{total_tokens:,}</p>
            </div>
            <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <p class="text-[10px] text-gray-500 uppercase">Total Calls</p>
                <p class="text-lg font-bold mono text-gray-200">{total_calls}</p>
            </div>
            <div class="bg-gray-900 border border-gray-800 rounded-lg p-3">
                <p class="text-[10px] text-gray-500 uppercase">Avg Cost/Call</p>
                <p class="text-lg font-bold mono text-gray-200">${avg_cost:.4f}</p>
            </div>
        </div>

        <!-- By Model -->
        <div class="bg-gray-900 border border-gray-800 rounded-lg">
            <div class="px-4 py-3 border-b border-gray-800">
                <h3 class="text-sm font-semibold text-gray-300">Cost by Model</h3>
            </div>
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-[10px] text-gray-500 uppercase border-b border-gray-800">
                        <th class="px-3 py-2 text-left">Model</th>
                        <th class="px-3 py-2 text-right">Calls</th>
                        <th class="px-3 py-2 text-right">Cost</th>
                    </tr>
                </thead>
                <tbody>{model_table}</tbody>
            </table>
        </div>

        <!-- By Trigger -->
        <div class="bg-gray-900 border border-gray-800 rounded-lg">
            <div class="px-4 py-3 border-b border-gray-800">
                <h3 class="text-sm font-semibold text-gray-300">Cost by Trigger</h3>
            </div>
            <table class="w-full text-sm">
                <thead>
                    <tr class="text-[10px] text-gray-500 uppercase border-b border-gray-800">
                        <th class="px-3 py-2 text-left">Trigger</th>
                        <th class="px-3 py-2 text-right">Calls</th>
                        <th class="px-3 py-2 text-right">Cost</th>
                    </tr>
                </thead>
                <tbody>{trigger_table}</tbody>
            </table>
        </div>
    </div>
    """
    return HTMLResponse(content=html)


@router.get("/{interaction_id}")
async def llm_detail(request: Request, interaction_id: str):
    """Full prompt/response view for an LLM interaction."""
    templates = request.app.state.templates

    interaction = llm_service.get_interaction(interaction_id)
    if interaction is None:
        raise HTTPException(status_code=404, detail=f"LLM interaction '{interaction_id}' not found")

    return templates.TemplateResponse(
        request,
        "llm/detail.html",
        {
            "active_page": "llm",
            "interaction": interaction,
        },
    )
