"""Agents routes — agent run list, detail, and aggregate metrics."""

import asyncio
import json
import time

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from src.web.services import agent_service
from src.web.services.research_service import STREAM_LOGS_DIR

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
    agent_types = agent_service.get_distinct_agent_types()

    return templates.TemplateResponse(
        request,
        "agents/index.html",
        {
            "active_page": "agents",
            "runs": runs,
            "metrics": metrics,
            "agent_types": agent_types,
            "filter_type": agent_type,
            "filter_status": status,
        },
    )


@router.post("/scan-sessions")
async def scan_cli_sessions(request: Request):
    """Import CLI terminal sessions as agent runs."""
    from src.web.services.session_scanner import import_all_cli_sessions

    try:
        count = import_all_cli_sessions()
        if count > 0:
            return HTMLResponse(
                f'<span class="text-emerald-400">Imported {count} CLI session{"s" if count != 1 else ""}</span>'
            )
        return HTMLResponse('<span class="text-gray-500">No new CLI sessions to import</span>')
    except Exception as e:
        return HTMLResponse(f'<span class="text-red-400">Error: {str(e)[:100]}</span>')


@router.get("/metrics")
async def agent_metrics_partial(request: Request):
    """HTMX partial: aggregate agent metrics. Auto-scans CLI sessions."""
    from src.web.services.session_scanner import maybe_auto_scan
    maybe_auto_scan()

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


@router.get("/ops")
async def agent_ops_center(request: Request):
    """Agent Operations Center — real-time agent monitoring with charts."""
    templates = request.app.state.templates

    active_runs = agent_service.get_active_runs()
    cost_by_day = agent_service.get_cost_by_day(days=14)
    agent_roi = agent_service.get_agent_roi()
    recent_events = agent_service.get_recent_events(limit=50)

    import json

    return templates.TemplateResponse(
        request,
        "agents/ops.html",
        {
            "active_page": "agents",
            "active_runs": active_runs,
            "cost_by_day_json": json.dumps(cost_by_day),
            "agent_roi_json": json.dumps(agent_roi),
            "recent_events": recent_events,
        },
    )


@router.get("/{run_id}/events")
async def agent_events_sse(run_id: str):
    """SSE endpoint: stream JSONL events from disk for a running agent.

    - Catches up late joiners by replaying all existing lines
    - Polls for new lines every 500ms while running
    - Checks DB status every 5s as fallback termination signal
    - Stops on completed/failed event or 15-min timeout
    """
    log_path = STREAM_LOGS_DIR / f"{run_id}.jsonl"

    async def event_generator():
        lines_sent = 0
        last_db_check = time.monotonic()
        deadline = time.monotonic() + 15 * 60  # 15-min timeout

        while time.monotonic() < deadline:
            # Read any new lines from the JSONL file
            new_lines = []
            if log_path.exists():
                try:
                    with open(log_path, "r") as f:
                        all_lines = f.readlines()
                    new_lines = all_lines[lines_sent:]
                except Exception:
                    pass

            for line in new_lines:
                line = line.strip()
                if not line:
                    continue
                lines_sent += 1
                yield f"data: {line}\n\n"

                # Check for terminal events
                try:
                    msg = json.loads(line)
                    evt = msg.get("event", "")
                    if evt in ("completed", "failed"):
                        return
                except (json.JSONDecodeError, TypeError):
                    pass

            # DB status check every 5s as fallback
            now = time.monotonic()
            if now - last_db_check > 5:
                last_db_check = now
                run = agent_service.get_run(run_id)
                if run:
                    status = run.get("status", "") if isinstance(run, dict) else getattr(run, "status", "")
                    if status in ("completed", "failed"):
                        # Drain any remaining lines before closing
                        if log_path.exists():
                            try:
                                with open(log_path, "r") as f:
                                    all_lines = f.readlines()
                                for line in all_lines[lines_sent:]:
                                    line = line.strip()
                                    if line:
                                        lines_sent += 1
                                        yield f"data: {line}\n\n"
                            except Exception:
                                pass
                        yield f"data: {json.dumps({'event': status, 'data': {}})}\n\n"
                        return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{run_id}/status")
async def agent_status_partial(run_id: str):
    """Return agent status as plain text for polling fallback."""
    run = agent_service.get_run(run_id)
    if run is None:
        return HTMLResponse("unknown")
    status = run.get("status", "") if isinstance(run, dict) else getattr(run, "status", "")
    return HTMLResponse(status)


@router.get("/{run_id}")
async def agent_detail(request: Request, run_id: str):
    """Agent run detail with findings and child runs."""
    templates = request.app.state.templates

    run = agent_service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Agent run '{run_id}' not found")

    children = agent_service.get_child_runs(run_id)
    events = agent_service.get_run_events(run_id)

    r_type = run.get("agent_type", "") if isinstance(run, dict) else getattr(run, "agent_type", "")
    r_label = f"{r_type} — {run_id[:8]}" if r_type else run_id[:8]

    run_status = run.get("status", "") if isinstance(run, dict) else getattr(run, "status", "")
    is_running = run_status == "running"

    # Check for stream replay log
    from src.web.services.research_service import has_stream_log
    _has_stream_log = has_stream_log(run_id)

    # Related documents
    from src.web.services import document_service
    produced_docs = document_service.get_documents_for_agent_run(run_id)

    return templates.TemplateResponse(
        request,
        "agents/detail.html",
        {
            "active_page": "agents",
            "run": run,
            "children": children,
            "events": events,
            "is_running": is_running,
            "has_stream_log": _has_stream_log,
            "produced_docs": produced_docs,
            "breadcrumbs": [
                {"label": "Agents", "url": "/agents"},
                {"label": r_label},
            ],
        },
    )
