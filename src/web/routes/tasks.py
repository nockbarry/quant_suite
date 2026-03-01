"""Tasks routes — trigger background operations and poll status."""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.web.services.task_manager import get_task_manager, TaskState

router = APIRouter()

# ── Action registry ──────────────────────────────────────────────────

ACTION_REGISTRY: dict[str, dict] = {
    "refresh_state": {
        "label": "Refresh State",
        "description": "Update unified state.json",
    },
    "operator_check": {
        "label": "Operator Check",
        "description": "Run one operator monitoring cycle",
    },
    "collect_data": {
        "label": "Collect Data",
        "description": "Run research prep (all sources)",
    },
    "research_quick": {
        "label": "Quick Research",
        "description": "Run a quick research cycle",
    },
    "research_full": {
        "label": "Full Research",
        "description": "Run a full research cycle",
    },
}


def _dispatch_action(action: str) -> str:
    """Dispatch an action to the task manager. Returns task_id."""
    tm = get_task_manager()

    if action == "refresh_state":
        async def _refresh():
            from src.synthesis.daemon import LiveDaemon
            daemon = LiveDaemon()
            state = await daemon.update_now()
            return f"State updated ({len(state) if isinstance(state, dict) else 'ok'})"
        return tm.submit_async_task("Refresh State", _refresh)

    elif action == "operator_check":
        def _check():
            from src.monitoring.operator_loop import OperatorLoop
            loop = OperatorLoop()
            obs = loop.operator_check(check_num=1)
            return loop.format_observation(obs) if hasattr(loop, 'format_observation') else str(obs)
        return tm.submit_task("Operator Check", _check)

    elif action == "collect_data":
        return tm.submit_subprocess(
            "Collect Data",
            ["python3", "scripts/research_prep.py"],
            timeout=600,
        )

    elif action == "research_quick":
        return tm.submit_subprocess(
            "Quick Research",
            ["python3", "scripts/full_research_cycle.py", "--quick"],
            timeout=600,
        )

    elif action == "research_full":
        return tm.submit_subprocess(
            "Full Research",
            ["python3", "scripts/full_research_cycle.py"],
            timeout=1800,
        )

    # Per-source refresh: collect_source:{name}
    elif action.startswith("collect_source:"):
        source_name = action.split(":", 1)[1]
        return _dispatch_source_refresh(source_name)

    else:
        raise ValueError(f"Unknown action: {action}")


def _dispatch_source_refresh(source: str) -> str:
    """Dispatch a per-source data refresh."""
    tm = get_task_manager()

    source_scripts = {
        "state.json": ("async", "_refresh_state"),
        "congressional": ("subprocess", ["python3", "scripts/cron_congressional_collect.py"]),
        "insider": ("subprocess", ["python3", "scripts/cron_insider_collect.py"]),
        "news": ("subprocess", ["python3", "scripts/cron_news_collect.py"]),
    }

    if source == "state.json":
        async def _refresh():
            from src.synthesis.daemon import LiveDaemon
            daemon = LiveDaemon()
            await daemon.update_now()
            return "State refreshed"
        return tm.submit_async_task(f"Refresh {source}", _refresh)

    entry = source_scripts.get(source)
    if entry and entry[0] == "subprocess":
        return tm.submit_subprocess(f"Refresh {source}", entry[1], timeout=300)

    # Fallback: submit a no-op that just reports source isn't scriptable
    def _noop():
        return f"Source '{source}' has no dedicated refresh script"
    return tm.submit_task(f"Refresh {source}", _noop)


# ── Routes ───────────────────────────────────────────────────────────

@router.post("/run/{action}")
async def run_action(request: Request, action: str):
    """Submit a named action and return a task status partial."""
    try:
        task_id = _dispatch_action(action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    task = get_task_manager().get_task(task_id)
    return HTMLResponse(_render_task_status(task))


@router.get("/{task_id}")
async def poll_task(request: Request, task_id: str):
    """Poll a task's current status (HTMX partial)."""
    task = get_task_manager().get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return HTMLResponse(_render_task_status(task))


@router.get("/badge/count")
async def task_badge(request: Request):
    """Return active task count for sidebar badge."""
    count = get_task_manager().active_count()
    if count == 0:
        return HTMLResponse("")
    return HTMLResponse(
        f'<span class="ml-1 inline-flex items-center justify-center w-4 h-4 text-[10px] '
        f'font-bold text-white bg-emerald-500 rounded-full">{count}</span>'
    )


# ── Rendering ────────────────────────────────────────────────────────

def _render_task_status(task) -> str:
    """Render a single task status as an HTMX-polling div."""
    if task is None:
        return ""

    is_terminal = task.state in (TaskState.COMPLETED, TaskState.FAILED)

    # HTMX polling attribute (only while non-terminal)
    poll_attr = "" if is_terminal else (
        f' hx-get="/tasks/{task.id}" hx-trigger="every 2s" hx-swap="outerHTML"'
    )

    if task.state == TaskState.PENDING:
        icon = '<span class="inline-block w-2 h-2 rounded-full bg-yellow-500 animate-pulse"></span>'
        label = "Queued..."
        extra = ""
    elif task.state == TaskState.RUNNING:
        icon = (
            '<svg class="animate-spin w-3 h-3 text-emerald-400" xmlns="http://www.w3.org/2000/svg" '
            'fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" '
            'stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" '
            'fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>'
        )
        label = f"Running... ({task.elapsed_seconds:.0f}s)"
        extra = ""
    elif task.state == TaskState.COMPLETED:
        icon = '<span class="inline-block w-2 h-2 rounded-full bg-emerald-500"></span>'
        label = f"Done ({task.elapsed_seconds:.1f}s)"
        result_text = str(task.result)[:120] if task.result else ""
        extra = f'<p class="text-[10px] text-gray-500 truncate mt-0.5">{result_text}</p>' if result_text else ""
    else:  # FAILED
        icon = '<span class="inline-block w-2 h-2 rounded-full bg-red-500"></span>'
        label = "Failed"
        error_text = task.error[:120] if task.error else "Unknown error"
        extra = f'<p class="text-[10px] text-red-400 truncate mt-0.5">{error_text}</p>'

    return (
        f'<div id="task-{task.id}" class="flex items-start gap-2 px-3 py-1.5 text-xs"'
        f'{poll_attr}>'
        f'  <div class="mt-0.5 flex-shrink-0">{icon}</div>'
        f'  <div class="min-w-0 flex-1">'
        f'    <span class="text-gray-300">{task.name}</span>'
        f'    <span class="text-gray-500 ml-1">{label}</span>'
        f'    {extra}'
        f'  </div>'
        f'</div>'
    )
