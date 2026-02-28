"""Flows routes — process event timeline, decision flow, and causal chains."""

import html as html_mod
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.web.services import flow_service

router = APIRouter()


@router.get("/")
async def flow_list(request: Request):
    """Process event timeline with filters."""
    templates = request.app.state.templates

    # Parse query filters
    event_type = request.query_params.get("event_type")
    source = request.query_params.get("source")
    severity = request.query_params.get("severity")
    symbol = request.query_params.get("symbol")
    limit = int(request.query_params.get("limit", 100))

    events = flow_service.list_events(
        event_type=event_type,
        source=source,
        severity=severity,
        symbol=symbol,
        limit=limit,
    )

    # Collect distinct values for filter dropdowns
    filter_options = flow_service.get_filter_options()

    return templates.TemplateResponse(
        request,
        "flows/index.html",
        {
            "active_page": "flows",
            "events": events,
            "filter_options": filter_options,
            "filters": {
                "event_type": event_type,
                "source": source,
                "severity": severity,
                "symbol": symbol,
            },
        },
    )


@router.get("/decision/{decision_id}")
async def decision_flow(request: Request, decision_id: str):
    """Decision flow view: all events related to a specific decision."""
    templates = request.app.state.templates

    events = flow_service.get_decision_events(decision_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"No events found for decision '{decision_id}'")

    return templates.TemplateResponse(
        request,
        "flows/decision_flow.html",
        {
            "active_page": "flows",
            "decision_id": decision_id,
            "events": events,
        },
    )


@router.get("/chain/{event_id}")
async def causal_chain(request: Request, event_id: str):
    """Causal chain view: parent-child event chain for an event."""
    chain = flow_service.get_causal_chain(event_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    chain_list = chain if isinstance(chain, list) else [chain]

    parts = [
        '<div class="p-6 space-y-4">',
        f'<div><a href="/flows" class="text-gray-500 hover:text-gray-300 text-sm">&larr; Activity Stream</a>',
        f'<h1 class="text-xl font-bold text-gray-100 mt-1">Causal Chain</h1>',
        f'<p class="text-sm text-gray-500">Event chain from root <span class="mono">{html_mod.escape(event_id[:12])}</span></p></div>',
        '<div class="space-y-0">',
    ]

    for idx, evt in enumerate(chain_list):
        is_last = idx == len(chain_list) - 1
        parts.append(_render_chain_event(evt, is_last))

    parts.append("</div></div>")
    return HTMLResponse(content="".join(parts))


@router.get("/{event_id}")
async def event_detail(request: Request, event_id: str):
    """HTMX expandable event detail."""
    event = flow_service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    children = flow_service.get_child_events(event_id)

    html = _render_event_row(event, children)
    return HTMLResponse(content=html)


def _get_ev(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _render_event_row(event, children=None):
    """Render an event detail as inline HTML (mirrors components/event_row.html)."""
    etype = _get_ev(event, "event_type", "")
    source = _get_ev(event, "source", "")
    severity = _get_ev(event, "severity", "info")
    eid = _get_ev(event, "id", "")
    title = html_mod.escape(str(_get_ev(event, "title", "")))
    detail = _get_ev(event, "detail")
    symbol = _get_ev(event, "symbol")
    decision_id = _get_ev(event, "decision_id")
    thesis_id = _get_ev(event, "thesis_id")
    agent_run_id = _get_ev(event, "agent_run_id")
    signal_id = _get_ev(event, "signal_id")

    type_colors = {
        "trade": "bg-emerald-900/50 text-emerald-400",
        "signal": "bg-purple-900/50 text-purple-400",
        "decision": "bg-blue-900/50 text-blue-400",
        "alert": "bg-red-900/50 text-red-400",
        "agent": "bg-cyan-900/50 text-cyan-400",
        "llm": "bg-indigo-900/50 text-indigo-400",
        "thesis": "bg-amber-900/50 text-amber-400",
    }
    severity_colors = {
        "critical": "bg-red-900/50 text-red-400",
        "warning": "bg-yellow-900/50 text-yellow-400",
    }
    type_cls = type_colors.get(etype, "bg-gray-800 text-gray-400")
    sev_cls = severity_colors.get(severity, "bg-gray-800 text-gray-500")

    # Detail section
    detail_html = ""
    if detail:
        if isinstance(detail, dict):
            detail_content = f'<pre class="mono whitespace-pre-wrap">{html_mod.escape(json.dumps(detail, indent=2))}</pre>'
        else:
            detail_content = f'<p class="whitespace-pre-wrap">{html_mod.escape(str(detail))}</p>'
        detail_html = f'<div class="bg-gray-900 rounded p-2 text-xs text-gray-400 max-h-48 overflow-y-auto">{detail_content}</div>'

    # Links
    links = []
    if symbol:
        links.append(f'<a href="/knowledge/{html_mod.escape(str(symbol))}" class="text-emerald-400 hover:underline mono">{html_mod.escape(str(symbol))}</a>')
    if decision_id:
        links.append(f'<a href="/decisions/{html_mod.escape(str(decision_id))}" class="text-blue-400 hover:underline">Decision &rarr;</a>')
    if thesis_id:
        links.append(f'<a href="/theses/{html_mod.escape(str(thesis_id))}" class="text-amber-400 hover:underline">Thesis &rarr;</a>')
    if agent_run_id:
        links.append(f'<a href="/agents/{html_mod.escape(str(agent_run_id))}" class="text-cyan-400 hover:underline">Agent Run &rarr;</a>')
    if signal_id:
        links.append(f'<a href="/signals/{html_mod.escape(str(signal_id))}" class="text-purple-400 hover:underline">Signal &rarr;</a>')
    if decision_id:
        links.append(f'<a href="/flows/decision/{html_mod.escape(str(decision_id))}" class="text-gray-400 hover:text-gray-200">Full flow &rarr;</a>')

    links_html = f'<div class="flex items-center gap-3 mt-2 text-xs">{" ".join(links)}</div>' if links else ""

    # Children
    children_html = ""
    if children:
        child_parts = []
        for child in children:
            c_id = _get_ev(child, "id", "")
            c_title = html_mod.escape(str(_get_ev(child, "title", "")))
            c_type = _get_ev(child, "event_type", "")
            c_cls = type_colors.get(c_type, "bg-gray-800 text-gray-400")
            child_parts.append(
                f'<div class="flex items-center gap-2 px-3 py-1.5 hover:bg-gray-800/30 cursor-pointer" '
                f'hx-get="/flows/{html_mod.escape(str(c_id))}" hx-target="#child-detail-{html_mod.escape(str(c_id))}" hx-swap="innerHTML">'
                f'<span class="rounded-full px-2 py-0.5 text-[10px] {c_cls}">{html_mod.escape(str(c_type))}</span>'
                f'<span class="text-sm text-gray-400">{c_title}</span>'
                f'</div><div id="child-detail-{html_mod.escape(str(c_id))}"></div>'
            )
        children_html = f'<div class="mt-2 border-t border-gray-700 pt-2"><p class="text-[10px] text-gray-500 uppercase mb-1">Child Events</p>{" ".join(child_parts)}</div>'

    return f"""
    <div class="bg-gray-800/50 border border-gray-700 rounded-lg p-3 mt-1 fade-in">
        <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
                <span class="rounded-full px-2 py-0.5 text-[10px] {type_cls}">{html_mod.escape(str(etype))}</span>
                <span class="rounded-full px-2 py-0.5 text-[10px] bg-gray-800 text-gray-500">{html_mod.escape(str(source))}</span>
                <span class="rounded-full px-2 py-0.5 text-[10px] {sev_cls}">{html_mod.escape(str(severity))}</span>
            </div>
            <span class="text-[10px] text-gray-600 mono">{html_mod.escape(str(eid)[:12])}</span>
        </div>
        <p class="text-sm text-gray-300 mb-2">{title}</p>
        {detail_html}
        {links_html}
        {children_html}
    </div>
    """


def _render_chain_event(event, is_last=False):
    """Render a single event in a causal chain timeline."""
    etype = _get_ev(event, "event_type", "")
    title = html_mod.escape(str(_get_ev(event, "title", "")))
    source = html_mod.escape(str(_get_ev(event, "source", "")))
    timestamp = str(_get_ev(event, "timestamp", ""))[:16]
    eid = str(_get_ev(event, "id", ""))
    severity = _get_ev(event, "severity", "info")

    sev_dot = {"critical": "bg-red-500", "warning": "bg-yellow-500"}.get(severity, "bg-blue-500")
    type_colors = {
        "trade": "bg-emerald-900/50 text-emerald-400",
        "signal": "bg-purple-900/50 text-purple-400",
        "decision": "bg-blue-900/50 text-blue-400",
        "alert": "bg-red-900/50 text-red-400",
        "agent": "bg-cyan-900/50 text-cyan-400",
        "llm": "bg-indigo-900/50 text-indigo-400",
        "thesis": "bg-amber-900/50 text-amber-400",
    }
    type_cls = type_colors.get(etype, "bg-gray-800 text-gray-400")
    line = "" if is_last else '<div class="w-0.5 flex-1 min-h-[16px] bg-gray-800"></div>'

    return f"""
    <div class="flex gap-3">
        <div class="flex flex-col items-center w-6 flex-shrink-0">
            <div class="w-2.5 h-2.5 rounded-full mt-2 flex-shrink-0 {sev_dot}"></div>
            {line}
        </div>
        <div class="flex-1 pb-3 min-w-0">
            <div class="bg-gray-900 border border-gray-800 rounded-lg p-3 hover:border-gray-700 transition cursor-pointer"
                 hx-get="/flows/{html_mod.escape(eid)}" hx-target="#chain-detail-{html_mod.escape(eid)}" hx-swap="innerHTML">
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-xs text-gray-500 mono">{html_mod.escape(timestamp)}</span>
                    <span class="rounded-full px-2 py-0.5 text-[10px] {type_cls}">{html_mod.escape(etype)}</span>
                    <span class="rounded-full px-2 py-0.5 text-[10px] bg-gray-800 text-gray-500">{source}</span>
                </div>
                <p class="text-sm text-gray-300 mt-1">{title}</p>
            </div>
            <div id="chain-detail-{html_mod.escape(eid)}" class="mt-1"></div>
        </div>
    </div>
    """
