"""Decisions routes — trade decision list and full lineage view."""

import html as html_mod

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.web.services import decision_service

router = APIRouter()


@router.get("/")
async def decision_list(request: Request):
    """Decision list with optional filters."""
    templates = request.app.state.templates

    # Parse query filters
    symbol = request.query_params.get("symbol")
    action = request.query_params.get("action")
    status = request.query_params.get("status")
    thesis_id = request.query_params.get("thesis_id")
    setup_type = request.query_params.get("setup_type")
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    limit = int(request.query_params.get("limit", 50))

    decisions = decision_service.list_decisions(
        symbol=symbol,
        action=action,
        status=status,
        thesis_id=thesis_id,
        setup_type=setup_type,
        limit=limit,
    )

    # Get filter dropdown options
    thesis_options = decision_service.get_thesis_options()
    setup_types = decision_service.get_distinct_setup_types()

    return templates.TemplateResponse(
        request,
        "decisions/index.html",
        {
            "active_page": "decisions",
            "decisions": decisions,
            "filter_status": status,
            "filter_symbol": symbol,
            "filter_thesis": thesis_id,
            "filter_setup": setup_type,
            "filter_date_from": date_from,
            "filter_date_to": date_to,
            "thesis_options": thesis_options,
            "setup_types": setup_types,
            "breadcrumbs": [
                {"label": "Decisions"},
            ],
        },
    )


@router.get("/{decision_id}")
async def decision_detail(request: Request, decision_id: str):
    """Decision detail with full provenance lineage."""
    templates = request.app.state.templates

    decision = decision_service.get_decision(decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found")

    lineage = decision_service.get_decision_lineage(decision_id)

    from src.web.services import document_service
    related_docs = document_service.get_documents_for_decision(decision_id)

    d_symbol = decision.get("symbol", "") if isinstance(decision, dict) else getattr(decision, "symbol", "")
    d_label = f"{d_symbol} — {decision_id[:8]}" if d_symbol else decision_id[:8]

    return templates.TemplateResponse(
        request,
        "decisions/detail.html",
        {
            "active_page": "decisions",
            "decision": decision,
            "lineage": lineage,
            "related_docs": related_docs,
            "breadcrumbs": [
                {"label": "Decisions", "url": "/decisions"},
                {"label": d_label},
            ],
        },
    )


@router.get("/{decision_id}/lineage")
async def decision_lineage_partial(request: Request, decision_id: str):
    """HTMX partial: decision lineage chain (signals -> convergence -> LLM -> decision -> outcome)."""
    lineage = decision_service.get_decision_lineage(decision_id)
    if lineage is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found")

    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _esc(val):
        return html_mod.escape(str(val)) if val else ""

    steps = [
        ("signals", "Signals", "purple", "&#9889;"),
        ("convergence", "Convergence", "purple", "&#9733;"),
        ("briefing", "Briefing", "cyan", "&#9783;"),
        ("llm_analysis", "LLM Analysis", "indigo", "&#9041;"),
        ("adversarial", "Adversarial", "red", "&#9876;"),
        ("decision", "Decision", "blue", "&#9654;"),
        ("execution", "Execution", "emerald", "&#9632;"),
        ("outcome", "Outcome", "amber", "&#9679;"),
        ("learning", "Learning", "yellow", "&#9733;"),
    ]

    color_map = {
        "purple": ("bg-purple-500 border-purple-400", "text-purple-400"),
        "cyan": ("bg-cyan-500 border-cyan-400", "text-cyan-400"),
        "indigo": ("bg-indigo-500 border-indigo-400", "text-indigo-400"),
        "red": ("bg-red-500 border-red-400", "text-red-400"),
        "blue": ("bg-blue-500 border-blue-400", "text-blue-400"),
        "emerald": ("bg-emerald-500 border-emerald-400", "text-emerald-400"),
        "amber": ("bg-amber-500 border-amber-400", "text-amber-400"),
        "yellow": ("bg-yellow-500 border-yellow-400", "text-yellow-400"),
    }

    parts = ['<div class="space-y-0">']
    rendered_steps = []
    lineage_data = lineage if isinstance(lineage, dict) else {}

    for step_key, step_label, step_color, step_icon in steps:
        step_data = lineage_data.get(step_key)
        if step_data or step_key == "decision":
            rendered_steps.append((step_key, step_label, step_color, step_icon, step_data))

    for idx, (step_key, step_label, step_color, step_icon, step_data) in enumerate(rendered_steps):
        is_last = idx == len(rendered_steps) - 1
        dot_cls, text_cls = color_map.get(step_color, ("bg-gray-500 border-gray-400", "text-gray-400"))
        active_dot = dot_cls if step_data else "bg-gray-800 border-gray-600"
        opacity = "" if step_data else " opacity-40"

        line_html = "" if is_last else '<div class="w-0.5 flex-1 min-h-[12px] bg-gray-800"></div>'

        timestamp = ""
        if step_data:
            ts = _get(step_data, "timestamp")
            if ts:
                timestamp = f'<span class="text-[10px] text-gray-600 mono">{_esc(str(ts)[:16])}</span>'

        body = '<p class="text-xs text-gray-600">Not available</p>'
        if step_data:
            if step_key == "signals":
                count = _get(step_data, "count", 0)
                body = f'<span class="text-xs text-gray-500">{count} signals detected</span>'
            elif step_key == "convergence":
                sc = _get(step_data, "signal_count", 0)
                ws = _get(step_data, "weighted_score", 0)
                body = f'<p class="text-xs text-gray-400">{sc} aligned signals, score: <span class="mono text-purple-400">{ws:.2f}</span></p>'
            elif step_key == "briefing":
                summary = _esc(_get(step_data, "summary", "Briefing provided market context"))
                body = f'<p class="text-xs text-gray-400 truncate">{summary}</p>'
            elif step_key == "llm_analysis":
                summary = _esc(_get(step_data, "summary", "LLM analyzed signals and context"))
                body = f'<p class="text-xs text-gray-400 truncate">{summary}</p>'
            elif step_key == "adversarial":
                summary = _esc(_get(step_data, "summary", ""))
                concern = _get(step_data, "concern_level", "")
                c_cls = "text-red-400" if concern == "high" else ("text-yellow-400" if concern == "medium" else "text-gray-500")
                concern_html = f'<span class="text-[10px] {c_cls}">Concern: {_esc(concern)}</span>' if concern else ""
                body = f'<p class="text-xs text-gray-400">{summary}</p>{concern_html}'
            elif step_key == "decision":
                action = _esc(_get(step_data, "action", ""))
                conf = _get(step_data, "confidence", 0) or 0
                size = _get(step_data, "size_pct", 0) or 0
                a_cls = "bg-emerald-900/50 text-emerald-400" if action in ("BUY", "ADD") else ("bg-red-900/50 text-red-400" if action in ("SELL", "CLOSE") else "bg-gray-800 text-gray-400")
                body = f'<div class="flex items-center gap-2"><span class="rounded-full px-2 py-0.5 text-xs {a_cls}">{action}</span><span class="text-xs text-gray-400">{conf * 100:.0f}% confidence</span><span class="text-xs text-gray-500">{size:.1f}% size</span></div>'
            elif step_key == "execution":
                price = _get(step_data, "price")
                status = _get(step_data, "status", "")
                price_html = f'Price: <span class="mono">${price:.2f}</span>' if price else ""
                s_cls = "bg-emerald-900/50 text-emerald-400" if status == "filled" else ("bg-red-900/50 text-red-400" if status == "rejected" else "bg-gray-800 text-gray-400")
                status_html = f'<span class="rounded-full px-2 py-0.5 text-[10px] ml-1 {s_cls}">{_esc(status)}</span>' if status else ""
                body = f'<div class="text-xs text-gray-400">{price_html}{status_html}</div>'
            elif step_key == "outcome":
                pnl_pct = _get(step_data, "pnl_pct")
                pnl = _get(step_data, "pnl")
                hold = _get(step_data, "hold_days")
                parts_o = []
                if pnl_pct is not None:
                    p_cls = "text-profit" if pnl_pct >= 0 else "text-loss"
                    parts_o.append(f'<span class="mono font-medium {p_cls}">{pnl_pct:+.1f}%</span>')
                if pnl is not None:
                    parts_o.append(f'<span class="mono text-gray-500">${pnl:+.0f}</span>')
                if hold:
                    parts_o.append(f'<span class="text-gray-500">{hold}d hold</span>')
                body = f'<div class="flex items-center gap-2 text-xs">{" ".join(parts_o)}</div>'
            elif step_key == "learning":
                summary = _esc(_get(step_data, "summary", "Learning extracted"))
                body = f'<p class="text-xs text-gray-400 truncate">{summary}</p>'

        parts.append(f"""
        <div class="flex gap-3">
            <div class="flex flex-col items-center w-6">
                <div class="w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 {active_dot}"></div>
                {line_html}
            </div>
            <div class="flex-1 pb-2">
                <div class="bg-gray-800/30 border border-gray-800 rounded-lg p-3{opacity} transition">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="text-xs {text_cls}">{step_icon} {step_label}</span>
                        {timestamp}
                    </div>
                    {body}
                </div>
            </div>
        </div>
        """)

    parts.append("</div>")
    return HTMLResponse(content="".join(parts))
