"""Research console routes — run Claude Code or API sessions from the web UI."""

import html
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services.research_service import (
    RESEARCH_PRESETS,
    get_result_content,
    get_run_stream_log,
    get_running_research,
    is_api_available,
    list_results,
    run_research,
    run_research_streaming,
)
from src.web.services.task_manager import TaskState, get_task_manager

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def research_console(request: Request):
    """Render the research console page."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "research/index.html",
        {
            "request": request,
            "active_page": "research",
            "presets": RESEARCH_PRESETS,
            "history": list_results(limit=10),
            "api_available": is_api_available(),
        },
    )


@router.post("/run", response_class=HTMLResponse)
async def run_research_task(request: Request):
    """Submit a research task and return a polling partial."""
    form = await request.form()
    research_type = form.get("research_type", "custom")
    custom_prompt = form.get("custom_prompt", "").strip()
    mode = form.get("mode", "claude_code")

    # Validate mode
    if mode not in ("claude_code", "api"):
        mode = "claude_code"

    # Validate
    if research_type == "custom" and not custom_prompt:
        return HTMLResponse(
            '<div class="px-4 py-3 text-sm text-red-400 border border-red-800 rounded-lg">'
            "Enter a prompt for custom research.</div>"
        )

    if research_type not in RESEARCH_PRESETS and research_type != "custom":
        return HTMLResponse(
            '<div class="px-4 py-3 text-sm text-red-400 border border-red-800 rounded-lg">'
            f"Unknown research type: {html.escape(research_type)}</div>"
        )

    label = RESEARCH_PRESETS.get(research_type, {}).get("label", "Custom Research")
    mode_label = "API" if mode == "api" else "Claude Code"

    tm = get_task_manager()
    task_id = tm.submit_task(
        f"Research: {label}",
        run_research,
        research_type,
        custom_prompt,
        mode,
    )

    return HTMLResponse(_render_research_polling(task_id, label, mode_label))


@router.post("/run-stream", response_class=HTMLResponse)
async def run_research_stream(request: Request):
    """Submit a streaming research task and return live viewer HTML."""
    form = await request.form()
    research_type = form.get("research_type", "custom")
    custom_prompt = form.get("custom_prompt", "").strip()
    mode = form.get("mode", "claude_code")

    if mode not in ("claude_code", "api"):
        mode = "claude_code"

    if research_type == "custom" and not custom_prompt:
        return HTMLResponse(
            '<div class="px-4 py-3 text-sm text-red-400 border border-red-800 rounded-lg">'
            "Enter a prompt for custom research.</div>"
        )

    if research_type not in RESEARCH_PRESETS and research_type != "custom":
        return HTMLResponse(
            '<div class="px-4 py-3 text-sm text-red-400 border border-red-800 rounded-lg">'
            f"Unknown research type: {html.escape(research_type)}</div>"
        )

    label = RESEARCH_PRESETS.get(research_type, {}).get("label", "Custom Research")
    run_id = run_research_streaming(research_type, custom_prompt, mode)

    return HTMLResponse(_render_live_viewer(run_id, label, mode))


@router.get("/replay/{run_id}", response_class=HTMLResponse)
async def replay_research(request: Request, run_id: str):
    """Replay a saved research stream from JSONL."""
    templates = request.app.state.templates
    log = get_run_stream_log(run_id)
    if log is None:
        return HTMLResponse(
            '<div class="p-6 text-sm text-red-400">Stream log not found for this run.</div>',
            status_code=404,
        )

    return HTMLResponse(_render_replay_viewer(run_id, log))


@router.get("/result/{task_id}", response_class=HTMLResponse)
async def research_result(request: Request, task_id: str):
    """HTMX partial: render research result or keep polling."""
    tm = get_task_manager()
    task = tm.get_task(task_id)

    if task is None:
        return HTMLResponse(
            '<div class="px-4 py-3 text-sm text-red-400">Task not found.</div>'
        )

    if task.state in (TaskState.PENDING, TaskState.RUNNING):
        label = task.name.replace("Research: ", "")
        # Determine mode from running state or default
        running = get_running_research()
        mode_label = "API" if running and running.get("mode") == "api" else "Claude Code"
        return HTMLResponse(_render_research_polling(task_id, label, mode_label))

    if task.state == TaskState.FAILED:
        error = html.escape(task.error or "Unknown error")
        return HTMLResponse(
            f'<div class="border border-red-800 rounded-lg p-4">'
            f'<div class="flex items-center gap-2 mb-2">'
            f'<span class="w-2 h-2 rounded-full bg-red-500"></span>'
            f'<span class="text-sm font-medium text-red-400">Research Failed</span>'
            f'<span class="text-xs text-gray-500 ml-auto">{task.elapsed_seconds:.1f}s</span>'
            f"</div>"
            f'<pre class="text-xs text-red-300 whitespace-pre-wrap overflow-x-auto max-h-96">{error}</pre>'
            f"</div>"
        )

    # Completed
    result = task.result or {}
    content = html.escape(result.get("content", "No output"))
    elapsed = result.get("elapsed_seconds", task.elapsed_seconds)
    saved = result.get("saved_path", "")
    canonical = result.get("canonical_path", "")
    label = result.get("label", "Research")
    mode = result.get("mode", "claude_code")
    run_id = result.get("run_id", "")
    stderr = result.get("stderr", "")

    mode_badge = (
        '<span class="px-1.5 py-0.5 text-[10px] bg-blue-900/50 text-blue-400 rounded">API</span>'
        if mode == "api"
        else '<span class="px-1.5 py-0.5 text-[10px] bg-emerald-900/50 text-emerald-400 rounded">Claude Code</span>'
    )

    saved_html = ""
    if saved:
        filename = saved.split("/")[-1]
        saved_html = f'<span class="text-gray-500 ml-3 text-xs">Saved: {html.escape(filename)}</span>'

    canonical_html = ""
    if canonical:
        canonical_html = f'<span class="text-gray-500 ml-2 text-xs">&rarr; {html.escape(canonical.split("quant_results/")[-1])}</span>'

    agent_link = ""
    if run_id:
        agent_link = (
            f'<a href="/agents/{html.escape(run_id)}" '
            f'class="text-xs text-emerald-400 hover:underline ml-3">View agent run &rarr;</a>'
        )

    stderr_html = ""
    if stderr:
        stderr_html = (
            f'<details class="mt-2"><summary class="text-xs text-gray-600 cursor-pointer">stderr</summary>'
            f'<pre class="text-[10px] text-gray-600 mt-1 whitespace-pre-wrap">{html.escape(stderr)}</pre></details>'
        )

    return HTMLResponse(
        f'<div class="border border-gray-800 rounded-lg">'
        f'<div class="flex items-center gap-2 px-4 py-2 border-b border-gray-800 bg-gray-900/50">'
        f'<span class="w-2 h-2 rounded-full bg-emerald-500"></span>'
        f'<span class="text-sm font-medium text-emerald-400">{html.escape(label)}</span>'
        f'{mode_badge}'
        f'<span class="text-xs text-gray-500 ml-auto">{elapsed:.1f}s</span>'
        f"{saved_html}"
        f"{canonical_html}"
        f"{agent_link}"
        f"</div>"
        f'<div class="p-4 max-h-[600px] overflow-y-auto">'
        f'<pre class="text-xs text-gray-300 mono whitespace-pre-wrap leading-relaxed">{content}</pre>'
        f"{stderr_html}"
        f"</div>"
        f"</div>"
    )


@router.get("/status", response_class=HTMLResponse)
async def research_status(request: Request):
    """HTMX partial: compact research status for sidebar polling.

    Returns empty string if nothing running, or a compact status snippet.
    """
    running = get_running_research()
    if not running:
        # Check if any research task just completed (within last 10s)
        tm = get_task_manager()
        recent = tm.list_recent(limit=3)
        for t in recent:
            if t.name.startswith("Research:") and t.state == TaskState.COMPLETED:
                if t.completed_at and (time.time() - t.completed_at.timestamp()) < 10:
                    label = t.name.replace("Research: ", "")
                    return HTMLResponse(
                        f'<div class="flex items-center gap-1.5 text-emerald-400">'
                        f'<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>'
                        f'<a href="/research" class="text-[10px] hover:underline">Done: {html.escape(label)}</a>'
                        f'</div>'
                    )
        return HTMLResponse("")

    label = running.get("label", "Research")
    mode = running.get("mode", "claude_code")
    elapsed = int(time.time() - running.get("started_at", time.time()))
    task_id = running.get("task_id", "")
    mode_tag = "API" if mode == "api" else "CC"

    return HTMLResponse(
        f'<div class="flex items-center gap-1.5">'
        f'<svg class="animate-spin w-3 h-3 text-amber-400" xmlns="http://www.w3.org/2000/svg" '
        f'fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" '
        f'stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" '
        f'fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>'
        f'<a href="/research" class="text-[10px] text-amber-400 hover:underline">'
        f'{html.escape(label)} ({mode_tag}) {elapsed}s</a>'
        f'</div>'
    )


@router.get("/history", response_class=HTMLResponse)
async def research_history(request: Request):
    """HTMX partial: list past research results."""
    results = list_results(limit=20)
    if not results:
        return HTMLResponse(
            '<div class="px-4 py-6 text-center text-gray-600 text-sm">No past results</div>'
        )

    rows = []
    for r in results:
        rows.append(
            f'<a href="/research/view/{html.escape(r["filename"])}" '
            f'class="flex items-center justify-between px-4 py-2 hover:bg-gray-800/50 border-b border-gray-800/50 transition">'
            f'<div>'
            f'<span class="text-sm text-gray-300">{html.escape(r["label"])}</span>'
            f'<span class="text-xs text-gray-600 ml-2">{html.escape(r["timestamp"])}</span>'
            f"</div>"
            f'<span class="text-xs text-gray-600">{r["size_kb"]}KB</span>'
            f"</a>"
        )
    return HTMLResponse("".join(rows))


@router.get("/view/{filename}", response_class=HTMLResponse)
async def view_result(request: Request, filename: str):
    """View a saved research result."""
    content = get_result_content(filename)
    if content is None:
        templates = request.app.state.templates
        return templates.TemplateResponse(
            "research/index.html",
            {
                "request": request,
                "active_page": "research",
                "presets": RESEARCH_PRESETS,
                "history": list_results(limit=10),
                "api_available": is_api_available(),
                "error": "Result not found.",
            },
        )

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "research/index.html",
        {
            "request": request,
            "active_page": "research",
            "presets": RESEARCH_PRESETS,
            "history": list_results(limit=10),
            "api_available": is_api_available(),
            "viewed_content": content,
            "viewed_filename": filename,
        },
    )


def _render_research_polling(task_id: str, label: str, mode_label: str = "Claude Code") -> str:
    """Render a polling spinner for an in-progress research task."""
    mode_badge = (
        '<span class="px-1.5 py-0.5 text-[10px] bg-blue-900/50 text-blue-400 rounded ml-2">API</span>'
        if mode_label == "API"
        else '<span class="px-1.5 py-0.5 text-[10px] bg-emerald-900/50 text-emerald-400 rounded ml-2">Claude Code</span>'
    )
    return (
        f'<div id="research-result" '
        f'hx-get="/research/result/{task_id}" hx-trigger="every 3s" hx-swap="outerHTML">'
        f'<div class="border border-gray-800 rounded-lg p-6">'
        f'<div class="flex items-center gap-3">'
        f'<svg class="animate-spin w-5 h-5 text-emerald-400" xmlns="http://www.w3.org/2000/svg" '
        f'fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" '
        f'stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" '
        f'fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>'
        f'<div>'
        f'<p class="text-sm text-emerald-400 font-medium">Running: {html.escape(label)}{mode_badge}</p>'
        f'<p class="text-xs text-gray-500 mt-0.5">Session in progress... (up to 10 min for Claude Code, ~30s for API)</p>'
        f"</div>"
        f"</div>"
        f"</div>"
        f"</div>"
    )


def _render_live_viewer(run_id: str, label: str, mode: str) -> str:
    """Render the live streaming viewer with WebSocket connection."""
    mode_badge = (
        '<span class="px-1.5 py-0.5 text-[10px] bg-blue-900/50 text-blue-400 rounded">API</span>'
        if mode == "api"
        else '<span class="px-1.5 py-0.5 text-[10px] bg-emerald-900/50 text-emerald-400 rounded">Claude Code</span>'
    )
    esc_label = html.escape(label)
    esc_run_id = html.escape(run_id)

    return f'''
<div id="research-result" class="border border-gray-800 rounded-lg overflow-hidden">
    <!-- Header bar -->
    <div class="flex items-center gap-2 px-4 py-2 border-b border-gray-800 bg-gray-900/50" id="stream-header">
        <svg id="stream-spinner" class="animate-spin w-4 h-4 text-emerald-400" xmlns="http://www.w3.org/2000/svg"
             fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <span id="stream-status-dot" class="w-2 h-2 rounded-full bg-emerald-500 hidden"></span>
        <span class="text-sm font-medium text-emerald-400">{esc_label}</span>
        {mode_badge}
        <span id="stream-elapsed" class="text-xs text-gray-500 ml-auto mono">0s</span>
        <span class="text-gray-700 mx-1">|</span>
        <span id="stream-tokens" class="text-xs text-gray-500 mono">0 tokens</span>
        <span class="text-gray-700 mx-1">|</span>
        <span id="stream-cost" class="text-xs text-gray-500 mono">$0.0000</span>
    </div>

    <!-- Tab bar -->
    <div class="flex border-b border-gray-800 bg-gray-900/30">
        <button onclick="switchTab('output')" id="tab-output"
                class="stream-tab px-4 py-1.5 text-xs font-medium text-emerald-400 border-b-2 border-emerald-500">
            Output
        </button>
        <button onclick="switchTab('tools')" id="tab-tools"
                class="stream-tab px-4 py-1.5 text-xs font-medium text-gray-500 border-b-2 border-transparent hover:text-gray-300">
            Tools <span id="tools-count" class="ml-1 px-1.5 py-0.5 bg-gray-800 rounded text-[10px] text-gray-500">0</span>
        </button>
        <button onclick="switchTab('conversation')" id="tab-conversation"
                class="stream-tab px-4 py-1.5 text-xs font-medium text-gray-500 border-b-2 border-transparent hover:text-gray-300">
            Conversation
        </button>
        <div id="stream-final-links" class="ml-auto flex items-center gap-2 px-4 hidden">
            <a id="agent-run-link" href="/agents/{esc_run_id}"
               class="text-xs text-emerald-400 hover:underline">View agent run &rarr;</a>
        </div>
    </div>

    <!-- Content panels -->
    <div class="relative" style="min-height: 200px; max-height: 600px;">
        <!-- Output tab -->
        <div id="panel-output" class="stream-panel p-4 overflow-y-auto" style="max-height: 560px;">
            <pre id="stream-output" class="text-xs text-gray-300 mono whitespace-pre-wrap leading-relaxed"></pre>
            <span id="stream-cursor" class="inline-block w-1.5 h-3.5 bg-emerald-400 animate-pulse align-middle"></span>
        </div>

        <!-- Tools tab -->
        <div id="panel-tools" class="stream-panel p-4 overflow-y-auto hidden" style="max-height: 560px;">
            <div id="tools-container" class="space-y-3">
                <p class="text-xs text-gray-600">Tool calls will appear here...</p>
            </div>
        </div>

        <!-- Conversation tab -->
        <div id="panel-conversation" class="stream-panel p-4 overflow-y-auto hidden" style="max-height: 560px;">
            <div id="conversation-container" class="space-y-3">
                <p class="text-xs text-gray-600">Turn-by-turn conversation will appear here...</p>
            </div>
        </div>
    </div>
</div>

<script>
(function() {{
    const runId = "{esc_run_id}";
    const startTime = Date.now();
    let toolCount = 0;
    let currentTurn = 0;
    let turnContent = {{}};
    let ws = null;
    let reconnectAttempts = 0;

    // Elapsed timer
    const timerInterval = setInterval(function() {{
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const el = document.getElementById('stream-elapsed');
        if (el) {{
            if (elapsed < 60) el.textContent = elapsed + 's';
            else el.textContent = Math.floor(elapsed/60) + 'm ' + (elapsed%60) + 's';
        }}
    }}, 1000);

    function connect() {{
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(proto + '//' + location.host + '/ws/research/' + runId);

        ws.onopen = function() {{
            reconnectAttempts = 0;
        }};

        ws.onmessage = function(e) {{
            const msg = JSON.parse(e.data);
            handleEvent(msg);
        }};

        ws.onclose = function() {{
            // Reconnect if not completed
            const spinner = document.getElementById('stream-spinner');
            if (spinner && !spinner.classList.contains('hidden')) {{
                if (reconnectAttempts < 5) {{
                    reconnectAttempts++;
                    setTimeout(connect, 1000 * reconnectAttempts);
                }}
            }}
        }};
    }}

    function handleEvent(msg) {{
        const event = msg.event;
        const data = msg.data || {{}};

        switch (event) {{
            case 'text_delta':
                appendOutput(data.text || '');
                appendToTurn(data.turn, 'text', data.text || '');
                break;

            case 'tool_use_start':
                toolCount++;
                document.getElementById('tools-count').textContent = toolCount;
                addToolCard(data.name, data.id);
                appendToTurn(data.turn, 'tool_start', data.name);
                break;

            case 'tool_input_delta':
                appendToolInput(data.id, data.partial_json || '');
                break;

            case 'tool_use_end':
                finalizeToolCard(data.name);
                break;

            case 'thinking_delta':
                // Show thinking in conversation tab
                appendToTurn(data.turn, 'thinking', data.text || '');
                break;

            case 'turn_start':
                currentTurn = data.turn || 0;
                addTurnHeader(currentTurn, data.model || '');
                break;

            case 'turn_end':
                break;

            case 'tokens_update':
                updateTokens(data);
                break;

            case 'result':
                // Final result text from CLI — use if output is empty
                if (data.text) {{
                    const output = document.getElementById('stream-output');
                    if (output && !output.textContent.trim()) {{
                        output.textContent = data.text;
                    }}
                }}
                break;

            case 'completed':
                onCompleted(data);
                break;

            case 'failed':
                onFailed(data);
                break;

            case 'started':
                break;
        }}
    }}

    function appendOutput(text) {{
        const el = document.getElementById('stream-output');
        if (el) {{
            el.textContent += text;
            // Auto-scroll
            const panel = document.getElementById('panel-output');
            if (panel) panel.scrollTop = panel.scrollHeight;
        }}
    }}

    function addToolCard(name, toolId) {{
        const container = document.getElementById('tools-container');
        if (!container) return;
        // Remove placeholder
        const placeholder = container.querySelector('p.text-gray-600');
        if (placeholder) placeholder.remove();

        const card = document.createElement('div');
        card.id = 'tool-' + (toolId || toolCount);
        card.className = 'border border-gray-700 rounded-lg overflow-hidden';
        card.innerHTML =
            '<div class="flex items-center gap-2 px-3 py-1.5 bg-gray-800/50 border-b border-gray-700">' +
            '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>' +
            '<span class="text-xs font-medium text-amber-400">' + escHtml(name) + '</span>' +
            '<span class="text-[10px] text-gray-600 ml-auto mono">#' + toolCount + '</span>' +
            '</div>' +
            '<pre class="tool-input px-3 py-2 text-[11px] text-gray-400 mono whitespace-pre-wrap max-h-40 overflow-y-auto"></pre>';
        container.appendChild(card);
        const panel = document.getElementById('panel-tools');
        if (panel) panel.scrollTop = panel.scrollHeight;
    }}

    function appendToolInput(toolId, partial) {{
        // Append to most recent tool card
        const container = document.getElementById('tools-container');
        if (!container) return;
        const cards = container.querySelectorAll('.tool-input');
        const last = cards[cards.length - 1];
        if (last) last.textContent += partial;
    }}

    function finalizeToolCard(name) {{
        // Change indicator from amber pulse to gray
        const container = document.getElementById('tools-container');
        if (!container) return;
        const indicators = container.querySelectorAll('.animate-pulse');
        const last = indicators[indicators.length - 1];
        if (last) {{
            last.classList.remove('animate-pulse', 'bg-amber-400');
            last.classList.add('bg-gray-500');
        }}
    }}

    function addTurnHeader(turn, model) {{
        const container = document.getElementById('conversation-container');
        if (!container) return;
        const placeholder = container.querySelector('p.text-gray-600');
        if (placeholder) placeholder.remove();

        const header = document.createElement('div');
        header.className = 'flex items-center gap-2 pt-2';
        header.innerHTML =
            '<span class="text-xs font-semibold text-gray-400">Turn ' + turn + '</span>' +
            (model ? '<span class="text-[10px] text-gray-600 mono">' + escHtml(model) + '</span>' : '');
        container.appendChild(header);

        const content = document.createElement('pre');
        content.id = 'turn-content-' + turn;
        content.className = 'text-xs text-gray-300 mono whitespace-pre-wrap leading-relaxed mt-1 pl-3 border-l border-gray-800';
        container.appendChild(content);
    }}

    function appendToTurn(turn, type, text) {{
        const el = document.getElementById('turn-content-' + turn);
        if (!el) return;
        if (type === 'text') {{
            el.textContent += text;
        }} else if (type === 'tool_start') {{
            const badge = document.createElement('span');
            badge.className = 'inline-block px-1.5 py-0.5 my-1 text-[10px] bg-amber-900/30 text-amber-400 rounded';
            badge.textContent = 'Tool: ' + text;
            el.appendChild(badge);
            el.appendChild(document.createTextNode('\\n'));
        }} else if (type === 'thinking') {{
            // Show thinking in muted style
            const span = document.createElement('span');
            span.className = 'text-gray-600';
            span.textContent = text;
            el.appendChild(span);
        }}
        const panel = document.getElementById('panel-conversation');
        if (panel) panel.scrollTop = panel.scrollHeight;
    }}

    function updateTokens(data) {{
        const tokensEl = document.getElementById('stream-tokens');
        const costEl = document.getElementById('stream-cost');
        if (tokensEl) {{
            const total = (data.total_tokens || data.input_tokens + data.output_tokens || 0);
            tokensEl.textContent = total.toLocaleString() + ' tokens';
        }}
        if (costEl && data.cost_usd !== undefined) {{
            costEl.textContent = '$' + data.cost_usd.toFixed(4);
        }}
    }}

    function onCompleted(data) {{
        clearInterval(timerInterval);
        // Update elapsed
        const el = document.getElementById('stream-elapsed');
        if (el && data.elapsed_seconds) {{
            el.textContent = data.elapsed_seconds.toFixed(1) + 's';
        }}
        // Update tokens final
        updateTokens(data);
        // Hide spinner, show dot
        const spinner = document.getElementById('stream-spinner');
        if (spinner) spinner.classList.add('hidden');
        const dot = document.getElementById('stream-status-dot');
        if (dot) dot.classList.remove('hidden');
        // Hide cursor
        const cursor = document.getElementById('stream-cursor');
        if (cursor) cursor.classList.add('hidden');
        // Show final links + saved report links
        const linksEl = document.getElementById('stream-final-links');
        if (linksEl) {{
            linksEl.classList.remove('hidden');
            // Add saved report link if available
            if (data.canonical_path) {{
                const short = data.canonical_path.split('quant_results/').pop() || data.canonical_path;
                const reportLink = document.createElement('span');
                reportLink.className = 'text-xs text-gray-400';
                reportLink.innerHTML = 'Saved: <span class="text-gray-300">' + escHtml(short) + '</span>';
                linksEl.insertBefore(reportLink, linksEl.firstChild);
            }}
        }}
        // Close websocket
        if (ws) ws.close();
    }}

    function onFailed(data) {{
        clearInterval(timerInterval);
        const spinner = document.getElementById('stream-spinner');
        if (spinner) spinner.classList.add('hidden');
        const dot = document.getElementById('stream-status-dot');
        if (dot) {{
            dot.classList.remove('hidden', 'bg-emerald-500');
            dot.classList.add('bg-red-500');
        }}
        const cursor = document.getElementById('stream-cursor');
        if (cursor) cursor.classList.add('hidden');
        const output = document.getElementById('stream-output');
        if (output) {{
            output.textContent += '\\n\\n--- ERROR ---\\n' + (data.error || 'Unknown error');
            output.classList.add('text-red-400');
        }}
        if (ws) ws.close();
    }}

    function escHtml(str) {{
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }}

    // Tab switching
    window.switchTab = function(tab) {{
        document.querySelectorAll('.stream-tab').forEach(function(t) {{
            t.classList.remove('text-emerald-400', 'border-emerald-500');
            t.classList.add('text-gray-500', 'border-transparent');
        }});
        document.querySelectorAll('.stream-panel').forEach(function(p) {{
            p.classList.add('hidden');
        }});
        const tabBtn = document.getElementById('tab-' + tab);
        if (tabBtn) {{
            tabBtn.classList.remove('text-gray-500', 'border-transparent');
            tabBtn.classList.add('text-emerald-400', 'border-emerald-500');
        }}
        const panel = document.getElementById('panel-' + tab);
        if (panel) panel.classList.remove('hidden');
    }};

    connect();
}})();
</script>'''


def _render_replay_viewer(run_id: str, log_lines: list[str]) -> str:
    """Render a replay viewer that plays back saved JSONL events."""
    import json as _json

    esc_run_id = html.escape(run_id)

    # Parse events from log for the replay
    events_json = _json.dumps(log_lines)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Replay: {esc_run_id}</title>
<style>
body {{ background: #0d1117; color: #c9d1d9; font-family: monospace; margin: 0; padding: 24px; }}
.header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
.header h1 {{ font-size: 16px; font-weight: 600; }}
.header a {{ color: #10b981; font-size: 12px; }}
#replay-output {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px;
                  max-height: 70vh; overflow-y: auto; white-space: pre-wrap; font-size: 12px; line-height: 1.6; }}
.controls {{ margin-top: 12px; display: flex; gap: 8px; align-items: center; }}
.controls button {{ background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 4px 12px;
                    border-radius: 4px; cursor: pointer; font-size: 12px; }}
.controls button:hover {{ background: #30363d; }}
#replay-progress {{ flex: 1; height: 4px; background: #21262d; border-radius: 2px; overflow: hidden; }}
#replay-bar {{ height: 100%; background: #10b981; width: 0%; transition: width 0.1s; }}
</style>
</head>
<body>
<div class="header">
    <h1>Session Replay: {esc_run_id}</h1>
    <a href="/agents/{esc_run_id}">Back to agent run &rarr;</a>
    <a href="/research/">Back to console &rarr;</a>
</div>
<div id="replay-output"></div>
<div class="controls">
    <button onclick="startReplay()">Play</button>
    <button onclick="pauseReplay()">Pause</button>
    <button onclick="instantReplay()">Instant</button>
    <div id="replay-progress"><div id="replay-bar"></div></div>
    <span id="replay-counter" style="font-size:11px;color:#6b7280">0 / 0</span>
</div>
<script>
const rawLines = {events_json};
let idx = 0;
let playing = false;
let timer = null;

function startReplay() {{
    if (playing) return;
    playing = true;
    playNext();
}}

function pauseReplay() {{
    playing = false;
    if (timer) clearTimeout(timer);
}}

function instantReplay() {{
    pauseReplay();
    const output = document.getElementById('replay-output');
    output.textContent = '';
    for (let i = 0; i < rawLines.length; i++) {{
        processLine(rawLines[i]);
    }}
    idx = rawLines.length;
    updateProgress();
}}

function playNext() {{
    if (!playing || idx >= rawLines.length) {{
        playing = false;
        return;
    }}
    processLine(rawLines[idx]);
    idx++;
    updateProgress();
    timer = setTimeout(playNext, 30);
}}

function processLine(line) {{
    try {{
        const obj = JSON.parse(line);
        // Check for stream event wrapper
        if (obj.type === 'research_stream' && obj.data) {{
            const evt = obj.event;
            const data = obj.data;
            if (evt === 'text_delta' && data.text) {{
                document.getElementById('replay-output').textContent += data.text;
            }} else if (evt === 'tool_use_start' && data.name) {{
                document.getElementById('replay-output').textContent += '\\n[Tool: ' + data.name + ']\\n';
            }} else if (evt === 'completed') {{
                document.getElementById('replay-output').textContent += '\\n\\n--- Completed ---';
            }}
        }}
        // Raw stream-json lines from Claude CLI
        if (obj.type === 'assistant' && obj.message) {{
            const msg = obj.message;
            if (msg.type === 'content_block_delta') {{
                const delta = msg.delta || {{}};
                if (delta.type === 'text_delta' && delta.text) {{
                    document.getElementById('replay-output').textContent += delta.text;
                }}
            }}
        }}
        if (obj.type === 'result' && obj.result) {{
            // Show final result if no text was streamed
            const output = document.getElementById('replay-output');
            if (!output.textContent.trim()) {{
                output.textContent = obj.result;
            }}
        }}
    }} catch(e) {{}}
}}

function updateProgress() {{
    const pct = rawLines.length > 0 ? (idx / rawLines.length * 100) : 0;
    document.getElementById('replay-bar').style.width = pct + '%';
    document.getElementById('replay-counter').textContent = idx + ' / ' + rawLines.length;
}}

updateProgress();
</script>
</body>
</html>'''
