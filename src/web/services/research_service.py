"""Research service — dual-backend (Claude Code subprocess + Anthropic API).

Runs research sessions, logs to DB (AgentRun + ProcessEvent) and JSONL,
routes output to canonical directories, and exposes status for sidebar polling.
Supports live streaming via WebSocket for real-time visibility.
"""

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import yaml

logger = logging.getLogger(__name__)

CLAUDE_PATH = "/home/nock/.local/bin/claude"
RESULTS_DIR = Path.home() / "quant_results" / "research_results"
PROJECT_DIR = "/home/nock/projects/quant_suite"
QUANT_RESULTS = Path.home() / "quant_results"

# Preset research prompts
RESEARCH_PRESETS = {
    "morning_briefing": {
        "label": "Morning Briefing",
        "icon": "&#9788;",
        "color": "amber",
        "prompt": (
            "Read state.json and run a complete pre-market morning briefing. "
            "Include: market regime, overnight news, thesis status updates, "
            "signpost checks, key levels to watch, and prioritized action items "
            "for today. Save the briefing to ~/quant_results/briefings/."
        ),
    },
    "thesis_review": {
        "label": "Thesis Review",
        "icon": "&#9672;",
        "color": "emerald",
        "prompt": (
            "Read all active theses from ~/quant_results/theses/. For each: "
            "check current conviction vs signpost status, review recent price "
            "action, assess if any signposts have triggered. Summarize with "
            "recommended conviction changes."
        ),
    },
    "signal_scan": {
        "label": "Signal Scan",
        "icon": "&#9889;",
        "color": "purple",
        "prompt": (
            "Scan for current trading signals and alpha opportunities. Check "
            "state.json signals, look for convergences (3+ aligned signals), "
            "review social signals and news for any thesis-relevant catalysts. "
            "Prioritize actionable items."
        ),
    },
    "risk_check": {
        "label": "Risk Check",
        "icon": "&#9888;",
        "color": "red",
        "prompt": (
            "Run a portfolio risk check. Read state.json positions, check: "
            "concentration limits (10% single, 40% thesis, 45% sector), "
            "stop-loss proximity, regime alignment, PDT status. Flag any "
            "violations or concerns."
        ),
    },
    "eod_review": {
        "label": "EOD Review",
        "icon": "&#9790;",
        "color": "blue",
        "prompt": (
            "Run end-of-day review. Evaluate today's decisions vs outcomes, "
            "check thesis performance, extract learnings, update conviction "
            "levels where warranted, and prepare recommendations for tomorrow. "
            "Save the review to ~/quant_results/eod_reviews/."
        ),
    },
}

# Canonical output routing map
_CANONICAL_DIRS = {
    "morning_briefing": ("briefings", "briefing_{date}.md"),
    "thesis_review": ("theses/reviews", "review_{date}.md"),
    "signal_scan": ("live/research", "signal_scan_{datetime}.md"),
    "risk_check": ("live/research", "risk_check_{datetime}.md"),
    "eod_review": ("eod_reviews", "review_{date}.md"),
    "custom": ("research_results", "{datetime}_custom.md"),
}

# ---------------------------------------------------------------------------
# In-memory tracking for running research (for sidebar polling)
# Falls back to DB query for persistence across page navigations.
# ---------------------------------------------------------------------------

_running_research: dict | None = None  # {task_id, label, mode, started_at}

STREAM_LOGS_DIR = QUANT_RESULTS / "research_streams"


def _append_to_stream_log(run_id: str, message: dict) -> None:
    """Append a single broadcast event as a JSONL line (incremental write)."""
    try:
        STREAM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(STREAM_LOGS_DIR / f"{run_id}.jsonl", "a") as f:
            f.write(json.dumps(message) + "\n")
    except Exception:
        pass


def get_running_research() -> dict | None:
    """Return info about currently running research, or None.

    First checks in-memory state, then falls back to DB query for
    AgentRun rows with status='running' and research agent types.
    """
    if _running_research is not None:
        return _running_research

    # DB fallback — survives page navigation
    try:
        from src.db.database import get_db
        from src.db.models import AgentRun

        with get_db() as session:
            run = (
                session.query(AgentRun)
                .filter(
                    AgentRun.status == "running",
                    AgentRun.agent_type.in_(["research", "api_research"]),
                )
                .order_by(AgentRun.started_at.desc())
                .first()
            )
            if run:
                mode = "api" if run.agent_type == "api_research" else "claude_code"
                label = run.task.split(":")[0].strip() if ":" in run.task else run.task
                started = run.started_at.timestamp() if run.started_at else time.time()
                return {
                    "task_id": run.id,
                    "label": label,
                    "mode": mode,
                    "started_at": started,
                }
    except Exception as e:
        logger.debug(f"DB fallback for running research failed: {e}")

    return None


def _set_running(task_id: str, label: str, mode: str) -> None:
    global _running_research
    _running_research = {
        "task_id": task_id,
        "label": label,
        "mode": mode,
        "started_at": time.time(),
    }


def _clear_running() -> None:
    global _running_research
    _running_research = None


# ---------------------------------------------------------------------------
# API availability check
# ---------------------------------------------------------------------------


def is_api_available() -> bool:
    """Check if Anthropic API key is configured."""
    # Check credentials.yaml first
    creds_path = Path(PROJECT_DIR) / "config" / "credentials.yaml"
    if creds_path.exists():
        try:
            with open(creds_path) as f:
                creds = yaml.safe_load(f)
            key = (creds.get("anthropic") or {}).get("api_key", "")
            if key and key.strip():
                return True
        except Exception:
            pass

    # Fall back to env var
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(key and key.strip())


def _get_api_key() -> str | None:
    """Get the Anthropic API key from credentials or env."""
    creds_path = Path(PROJECT_DIR) / "config" / "credentials.yaml"
    if creds_path.exists():
        try:
            with open(creds_path) as f:
                creds = yaml.safe_load(f)
            key = (creds.get("anthropic") or {}).get("api_key", "")
            if key and key.strip():
                return key.strip()
        except Exception:
            pass
    return os.environ.get("ANTHROPIC_API_KEY")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_prompt(research_type: str, custom_prompt: str = "") -> str:
    """Build the full prompt for a research type."""
    if research_type == "custom":
        return custom_prompt

    preset = RESEARCH_PRESETS.get(research_type)
    if not preset:
        raise ValueError(f"Unknown research type: {research_type}")

    base = preset["prompt"]
    if custom_prompt:
        return f"{base}\n\nAdditional instructions: {custom_prompt}"
    return base


def _build_api_system_prompt() -> str:
    """Build a condensed system prompt for API mode with project context."""
    parts = [
        "You are an expert trading analyst for Project Athena, a hybrid intelligence trading system.",
        "",
        "KEY TRADING RULES:",
        "- NO OPTIONS TRADING (averaged -14.25% return)",
        "- HOLD positions (exits averaged -6.66%, holdings +7.75%)",
        "- Equal weight within theses",
        "- Max 10% single position, 40% single thesis, 45% sector",
        "- Exit ONLY on: signpost invalidation, -15% stop, conviction <40%, concentration",
        "",
    ]

    # Try to load current state summary
    state_path = QUANT_RESULTS / "live" / "state.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            portfolio = state.get("portfolio", {})
            parts.append("CURRENT PORTFOLIO:")
            parts.append(f"- Equity: ${portfolio.get('equity', 'N/A')}")
            parts.append(f"- Cash: ${portfolio.get('cash', 'N/A')}")
            parts.append(f"- Positions: {portfolio.get('position_count', 'N/A')}")
            regime = state.get("market_regime", {})
            parts.append(f"- Market regime: {regime.get('regime', 'unknown')}")
            parts.append("")
        except Exception:
            pass

    # Try to load active theses
    theses_dir = QUANT_RESULTS / "theses"
    if theses_dir.exists():
        try:
            thesis_names = []
            for tf in sorted(theses_dir.glob("*.yaml"))[:10]:
                with open(tf) as f:
                    thesis = yaml.safe_load(f)
                if thesis and thesis.get("status") == "active":
                    name = thesis.get("name", tf.stem)
                    conv = thesis.get("conviction", "?")
                    thesis_names.append(f"  - {name} (conviction: {conv}%)")
            if thesis_names:
                parts.append("ACTIVE THESES:")
                parts.extend(thesis_names)
                parts.append("")
        except Exception:
            pass

    parts.extend([
        "KEY PATHS:",
        "- State: ~/quant_results/live/state.json",
        "- Theses: ~/quant_results/theses/",
        "- Learnings: ~/quant_results/learnings/",
        "- Decisions: ~/quant_results/decisions/",
        "",
        "Be concise and actionable. Use data to support claims.",
    ])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# DB + JSONL logging helpers
# ---------------------------------------------------------------------------


def _create_agent_run(research_type: str, mode: str, label: str, prompt_preview: str) -> str:
    """Insert AgentRun row at start. Also log to JSONL."""
    run_id = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"

    agent_type = "research" if mode == "claude_code" else "api_research"
    task_desc = f"{label}: {prompt_preview[:100]}" if prompt_preview else f"{label}: preset"

    try:
        from src.db.database import get_db
        from src.db.models import AgentRun

        with get_db() as session:
            run = AgentRun(
                id=run_id,
                agent_type=agent_type,
                task=task_desc,
                trigger_reason="web_dashboard",
                status="running",
            )
            session.add(run)
    except Exception as e:
        logger.warning(f"Failed to create agent_run in DB: {e}")

    # JSONL log
    try:
        from src.monitoring.agent_monitor import get_agent_monitor, AgentType

        monitor = get_agent_monitor()
        monitor.start_agent(AgentType.RESEARCH, f"Web: {label}")
    except Exception as e:
        logger.warning(f"Failed to log to JSONL: {e}")

    return run_id


def _index_research_document(run_id: str, result: dict) -> None:
    """Index the research output file in the documents table."""
    try:
        from src.db.write_api import athena_db

        file_path = result.get("canonical_path") or result.get("saved_path")
        if not file_path:
            return

        research_type = result.get("research_type", "custom")
        label = result.get("label", "Research Output")

        # Map research types to document types
        type_map = {
            "morning_briefing": "briefing",
            "thesis_review": "thesis_review",
            "signal_scan": "research_result",
            "risk_check": "research_result",
            "eod_review": "eod_review",
            "custom": "research_result",
        }
        doc_type = type_map.get(research_type, "research_result")

        # Extract symbols from content if present
        content = result.get("content", "")
        symbols = []
        import re
        for match in re.findall(r'\b([A-Z]{1,5})\b', content[:2000]):
            if match not in ("THE", "AND", "FOR", "BUT", "NOT", "ARE", "WAS",
                             "HAS", "HAD", "ITS", "ALL", "NEW", "NOW", "GET",
                             "MAY", "CAN", "SAY", "USE", "TRY", "RUN", "SET",
                             "TOP", "LOW", "HIGH", "BUY", "SELL", "HOLD",
                             "ETF", "IPO", "SEC", "FDA", "FED", "GDP", "CPI",
                             "CEO", "CFO", "COO", "RSI", "ATH", "YOY", "QOQ",
                             "LLM", "API", "USD", "EUR", "GBP", "JPY"):
                symbols.append(match)
        symbols = list(dict.fromkeys(symbols))[:10]  # Dedupe, max 10

        athena_db.save_document(
            doc_type=doc_type,
            title=label,
            file_path=file_path,
            source=f"web_research:{research_type}",
            agent_run_id=run_id,
            symbols=symbols,
            tags=[research_type, "web_dashboard"],
        )
        logger.info(f"Indexed research document: {label} -> {file_path}")
    except Exception as e:
        logger.warning(f"Failed to index research document: {e}")


def _complete_agent_run(run_id: str, result: dict) -> None:
    """Update AgentRun with results on success."""
    try:
        from src.db.database import get_db
        from src.db.models import AgentRun

        content = result.get("content", "")
        elapsed = result.get("elapsed_seconds", 0)
        mode = result.get("mode", "claude_code")

        with get_db() as session:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.findings_summary = content
                run.raw_output = content
                # Populate artifacts
                stream_log = STREAM_LOGS_DIR / f"{run_id}.jsonl"
                run.artifacts = json.dumps({
                    "canonical_path": result.get("canonical_path"),
                    "saved_path": result.get("saved_path"),
                    "stream_log_path": str(stream_log) if stream_log.exists() else None,
                })
    except Exception as e:
        logger.warning(f"Failed to complete agent_run in DB: {e}")

    # Index the output file as a document
    _index_research_document(run_id, result)

    # Create ProcessEvent
    try:
        from src.db.database import get_db
        from src.db.models import ProcessEvent

        with get_db() as session:
            event = ProcessEvent(
                id=f"evt_{run_id}",
                event_type="research_completed",
                source="web_dashboard",
                severity="info",
                title=f"Research: {result.get('label', 'Unknown')}",
                detail=json.dumps({
                    "elapsed": result.get("elapsed_seconds", 0),
                    "mode": result.get("mode", "claude_code"),
                    "saved_path": result.get("saved_path", ""),
                    "canonical_path": result.get("canonical_path", ""),
                }),
                agent_run_id=run_id,
            )
            session.add(event)
    except Exception as e:
        logger.warning(f"Failed to create process event: {e}")


def _fail_agent_run(run_id: str, error_msg: str) -> None:
    """Update AgentRun on failure."""
    try:
        from src.db.database import get_db
        from src.db.models import AgentRun

        with get_db() as session:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.status = "failed"
                run.completed_at = datetime.utcnow()
                run.findings_summary = f"FAILED: {error_msg[:5000]}"
    except Exception as e:
        logger.warning(f"Failed to mark agent_run as failed: {e}")


# ---------------------------------------------------------------------------
# Output routing
# ---------------------------------------------------------------------------


def _save_to_canonical_dir(research_type: str, content: str, label: str) -> str | None:
    """Save output to the canonical directory for this research type."""
    mapping = _CANONICAL_DIRS.get(research_type)
    if not mapping:
        return None

    subdir, pattern = mapping
    target_dir = QUANT_RESULTS / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    filename = (
        pattern
        .replace("{date}", now.strftime("%Y%m%d"))
        .replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
    )
    filepath = target_dir / filename

    header = (
        f"# {label}\n\n"
        f"**Time**: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Type**: {research_type}\n"
        f"**Source**: Web Dashboard\n\n---\n\n"
    )
    filepath.write_text(header + content)
    return str(filepath)


def _save_to_research_results(research_type: str, label: str, prompt: str, content: str, mode: str) -> Path | None:
    """Save a copy to research_results/ for unified history."""
    if not content.strip():
        return None

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{research_type}.md"
    filepath = RESULTS_DIR / filename

    header = (
        f"# {label}\n\n"
        f"**Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"**Type**: {research_type}\n"
        f"**Mode**: {mode}\n"
        f"**Prompt**: {prompt[:200]}\n\n---\n\n"
    )
    filepath.write_text(header + content)
    return filepath


# ---------------------------------------------------------------------------
# Execution backends
# ---------------------------------------------------------------------------


def _run_claude_code(research_type: str, custom_prompt: str) -> dict:
    """Run research via Claude Code subprocess (full tool access)."""
    prompt = _build_prompt(research_type, custom_prompt)
    label = RESEARCH_PRESETS.get(research_type, {}).get("label", "Custom Research")

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    start = time.time()
    try:
        result = subprocess.run(
            [CLAUDE_PATH, "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=PROJECT_DIR,
            env=env,
        )
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "content": "Research timed out after 10 minutes.",
            "error": True,
            "research_type": research_type,
            "label": label,
            "mode": "claude_code",
            "saved_path": None,
            "canonical_path": None,
            "elapsed_seconds": elapsed,
        }

    elapsed = time.time() - start
    content = result.stdout or ""
    error = result.stderr or ""

    if result.returncode != 0 and not content:
        content = f"Error (exit code {result.returncode}):\n{error}"

    return {
        "content": content,
        "stderr": error[:500] if error else "",
        "error": result.returncode != 0,
        "research_type": research_type,
        "label": label,
        "mode": "claude_code",
        "saved_path": None,  # filled by caller
        "canonical_path": None,  # filled by caller
        "elapsed_seconds": elapsed,
    }


def _run_api(research_type: str, custom_prompt: str) -> dict:
    """Run research via direct Anthropic API call (fast, no tool access)."""
    prompt = _build_prompt(research_type, custom_prompt)
    label = RESEARCH_PRESETS.get(research_type, {}).get("label", "Custom Research")

    api_key = _get_api_key()
    if not api_key:
        return {
            "content": "Anthropic API key not configured. Add it to config/credentials.yaml under anthropic.api_key.",
            "error": True,
            "research_type": research_type,
            "label": label,
            "mode": "api",
            "saved_path": None,
            "canonical_path": None,
            "elapsed_seconds": 0,
        }

    system = _build_api_system_prompt()

    start = time.time()
    try:
        from src.agents.llm_agent import ClaudeClient, LLMModel

        client = ClaudeClient(api_key=api_key, model=LLMModel.CLAUDE_SONNET, max_tokens=4096)

        # Run async in a new event loop (we're in a thread)
        loop = asyncio.new_event_loop()
        try:
            content = loop.run_until_complete(client.generate(prompt, system=system))
        finally:
            loop.close()

    except ImportError:
        content = "anthropic library not installed. Run: pip install anthropic"
        elapsed = time.time() - start
        return {
            "content": content,
            "error": True,
            "research_type": research_type,
            "label": label,
            "mode": "api",
            "saved_path": None,
            "canonical_path": None,
            "elapsed_seconds": elapsed,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "content": f"API error: {e}",
            "error": True,
            "research_type": research_type,
            "label": label,
            "mode": "api",
            "saved_path": None,
            "canonical_path": None,
            "elapsed_seconds": elapsed,
        }

    elapsed = time.time() - start
    return {
        "content": content,
        "stderr": "",
        "error": False,
        "research_type": research_type,
        "label": label,
        "mode": "api",
        "saved_path": None,
        "canonical_path": None,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------


def run_research(research_type: str, custom_prompt: str = "", mode: str = "claude_code") -> dict:
    """Run research, log to DB, save to canonical dirs.

    This is the main entry point called by the task manager.
    """
    label = RESEARCH_PRESETS.get(research_type, {}).get("label", "Custom Research")

    # Track running state for sidebar
    _set_running("pending", label, mode)

    # Create DB record
    run_id = _create_agent_run(research_type, mode, label, custom_prompt)
    _set_running(run_id, label, mode)

    try:
        # Dispatch to backend
        if mode == "api":
            result = _run_api(research_type, custom_prompt)
        else:
            result = _run_claude_code(research_type, custom_prompt)

        # Attach run_id to result
        result["run_id"] = run_id

        content = result.get("content", "")
        prompt = _build_prompt(research_type, custom_prompt) if research_type != "custom" or custom_prompt else ""

        if not result.get("error") and content.strip():
            # Save to canonical directory
            canonical = _save_to_canonical_dir(research_type, content, label)
            result["canonical_path"] = canonical

            # Also save to research_results/
            saved = _save_to_research_results(research_type, label, prompt, content, mode)
            result["saved_path"] = str(saved) if saved else None
        else:
            # Still save errors to research_results for history
            saved = _save_to_research_results(research_type, label, prompt, content, mode)
            result["saved_path"] = str(saved) if saved else None

        # Update DB record
        if not result.get("error"):
            _complete_agent_run(run_id, result)
        else:
            _fail_agent_run(run_id, content[:200])

        return result

    except Exception as e:
        _fail_agent_run(run_id, str(e))
        raise
    finally:
        _clear_running()


# ---------------------------------------------------------------------------
# History helpers (unchanged API)
# ---------------------------------------------------------------------------


def list_results(limit: int = 20) -> list[dict]:
    """List past research results from disk."""
    if not RESULTS_DIR.exists():
        return []

    files = sorted(RESULTS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    results = []
    for f in files[:limit]:
        parts = f.stem.split("_", 2)
        rtype = parts[2] if len(parts) > 2 else "unknown"
        label = RESEARCH_PRESETS.get(rtype, {}).get("label", rtype.replace("_", " ").title())
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size = f.stat().st_size

        results.append({
            "filename": f.name,
            "label": label,
            "research_type": rtype,
            "timestamp": mtime.strftime("%Y-%m-%d %H:%M"),
            "size_kb": f"{size / 1024:.1f}",
            "path": str(f),
        })
    return results


def get_result_content(filename: str) -> str | None:
    """Read a saved research result by filename."""
    filepath = RESULTS_DIR / filename
    if filepath.exists() and filepath.suffix == ".md":
        return filepath.read_text()
    return None


# ---------------------------------------------------------------------------
# Streaming entry point
# ---------------------------------------------------------------------------


def run_research_streaming(
    research_type: str, custom_prompt: str = "", mode: str = "claude_code"
) -> str:
    """Start a streaming research run in a background thread.

    Returns the run_id immediately. The caller should render a live viewer
    that connects to /ws/research/{run_id} for real-time updates.
    """
    label = RESEARCH_PRESETS.get(research_type, {}).get("label", "Custom Research")
    run_id = _create_agent_run(research_type, mode, label, custom_prompt)
    _set_running(run_id, label, mode)

    if mode == "api":
        target = _run_api_streaming
    else:
        target = _run_claude_code_streaming

    thread = threading.Thread(
        target=target,
        args=(run_id, research_type, custom_prompt, label),
        daemon=True,
        name=f"research-stream-{run_id}",
    )
    thread.start()
    return run_id


# ---------------------------------------------------------------------------
# Claude Code streaming backend
# ---------------------------------------------------------------------------


def _broadcast_sync(run_id: str, event: str, data: dict, seq: int) -> None:
    """Thread-safe broadcast helper."""
    from src.web.routes.websocket import broadcast_research_event_sync

    message = {
        "type": "research_stream",
        "run_id": run_id,
        "event": event,
        "data": data,
        "seq": seq,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    _append_to_stream_log(run_id, message)  # always works — disk-based
    broadcast_research_event_sync(run_id, message)  # best-effort — in-memory


def _run_claude_code_streaming(
    run_id: str, research_type: str, custom_prompt: str, label: str
) -> None:
    """Background thread: run Claude Code with stream-json and broadcast events."""
    from src.web.services.stream_parser import StreamEventParser

    prompt = _build_prompt(research_type, custom_prompt)
    parser = StreamEventParser()
    seq = 0
    start = time.time()

    # Broadcast started
    _broadcast_sync(run_id, "started", {"label": label, "mode": "claude_code"}, seq)
    seq += 1

    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    # Start heartbeat thread for agent liveness tracking
    _hb_stop = threading.Event()

    def _hb_loop():
        while not _hb_stop.wait(30):
            try:
                from src.db.write_api import athena_db
                athena_db.heartbeat_agent(run_id)
            except Exception:
                pass

    _hb_thread = threading.Thread(target=_hb_loop, daemon=True, name=f"hb-{run_id[:20]}")
    _hb_thread.start()

    try:
        proc = subprocess.Popen(
            [
                CLAUDE_PATH, "-p", prompt,
                "--output-format", "stream-json",
                "--verbose",
                "--include-partial-messages",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=PROJECT_DIR,
            env=env,
        )

        # Claude CLI stream-json outputs events on stderr, not stdout
        for line in proc.stderr:
            event = parser.parse_line(line)
            if event is None:
                continue

            _broadcast_sync(run_id, event.type, event.data, seq)
            seq += 1

            # After turn_end or result, send cumulative token update
            if event.type in ("turn_end", "result"):
                summary = parser.get_token_summary()
                _broadcast_sync(run_id, "tokens_update", summary, seq)
                seq += 1

        proc.wait(timeout=30)
        stdout_leftover = proc.stdout.read() if proc.stdout else ""
        elapsed = time.time() - start

        # Use accumulated text_delta content; fall back to result text if empty
        content = parser.full_text or parser._result_text
        token_summary = parser.get_token_summary()

        if proc.returncode != 0 and not content:
            content = f"Error (exit code {proc.returncode})"
            _fail_agent_run(run_id, content[:200])
            _broadcast_sync(run_id, "failed", {"error": content[:500]}, seq)
        else:
            result = {
                "content": content,
                "label": label,
                "mode": "claude_code",
                "research_type": research_type,
                "elapsed_seconds": elapsed,
            }

            # Save outputs
            prompt_text = _build_prompt(research_type, custom_prompt)
            if content.strip():
                canonical = _save_to_canonical_dir(research_type, content, label)
                result["canonical_path"] = canonical
                saved = _save_to_research_results(research_type, label, prompt_text, content, "claude_code")
                result["saved_path"] = str(saved) if saved else None

            _complete_agent_run_with_tokens(run_id, result, token_summary)
            _create_llm_interaction(run_id, label, prompt_text, content, token_summary, elapsed)
            _save_stream_log(run_id, parser.raw_lines)

            _broadcast_sync(
                run_id,
                "completed",
                {
                    "elapsed_seconds": round(elapsed, 1),
                    "run_id": run_id,
                    **token_summary,
                    "saved_path": result.get("saved_path", ""),
                    "canonical_path": result.get("canonical_path", ""),
                },
                seq,
            )

    except subprocess.TimeoutExpired:
        proc.kill()
        _fail_agent_run(run_id, "Process timed out")
        _broadcast_sync(run_id, "failed", {"error": "Process timed out after 10 minutes"}, seq)
    except Exception as e:
        logger.exception(f"Streaming research failed: {e}")
        _fail_agent_run(run_id, str(e))
        _broadcast_sync(run_id, "failed", {"error": str(e)[:500]}, seq)
    finally:
        _hb_stop.set()
        _clear_running()
        # Schedule buffer cleanup after 5 minutes
        def _cleanup():
            time.sleep(300)
            from src.web.routes.websocket import cleanup_research_buffer
            cleanup_research_buffer(run_id)

        threading.Thread(target=_cleanup, daemon=True).start()


# ---------------------------------------------------------------------------
# API streaming backend
# ---------------------------------------------------------------------------


def _run_api_streaming(
    run_id: str, research_type: str, custom_prompt: str, label: str
) -> None:
    """Background thread: run Anthropic API with streaming and broadcast events."""
    prompt = _build_prompt(research_type, custom_prompt)
    seq = 0
    start = time.time()

    _broadcast_sync(run_id, "started", {"label": label, "mode": "api"}, seq)
    seq += 1

    api_key = _get_api_key()
    if not api_key:
        _fail_agent_run(run_id, "No API key configured")
        _broadcast_sync(run_id, "failed", {"error": "Anthropic API key not configured"}, seq)
        _clear_running()
        return

    system = _build_api_system_prompt()
    full_text = ""
    input_tokens = 0
    output_tokens = 0
    model = "claude-sonnet-4-20250514"

    # Start heartbeat thread
    _hb_stop_api = threading.Event()

    def _hb_loop_api():
        while not _hb_stop_api.wait(30):
            try:
                from src.db.write_api import athena_db
                athena_db.heartbeat_agent(run_id)
            except Exception:
                pass

    _hb_thread_api = threading.Thread(target=_hb_loop_api, daemon=True, name=f"hb-api-{run_id[:16]}")
    _hb_thread_api.start()

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        # Emit turn start
        _broadcast_sync(run_id, "turn_start", {"turn": 1, "model": model}, seq)
        seq += 1

        with client.messages.stream(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                _broadcast_sync(run_id, "text_delta", {"text": text, "turn": 1}, seq)
                seq += 1

            # Get final message for token counts
            final = stream.get_final_message()
            input_tokens = final.usage.input_tokens
            output_tokens = final.usage.output_tokens

        elapsed = time.time() - start

        # Cost calculation
        from src.web.services.stream_parser import MODEL_COSTS
        costs = MODEL_COSTS.get(model, {"input": 3.0, "output": 15.0})
        cost_usd = round(
            (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000, 6
        )

        token_summary = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "model": model,
            "cost_usd": cost_usd,
        }

        # Emit turn end and token update
        _broadcast_sync(run_id, "turn_end", {"turn": 1, "output_tokens": output_tokens}, seq)
        seq += 1
        _broadcast_sync(run_id, "tokens_update", token_summary, seq)
        seq += 1

        # Save outputs
        result = {
            "content": full_text,
            "label": label,
            "mode": "api",
            "research_type": research_type,
            "elapsed_seconds": elapsed,
        }

        if full_text.strip():
            canonical = _save_to_canonical_dir(research_type, full_text, label)
            result["canonical_path"] = canonical
            saved = _save_to_research_results(research_type, label, prompt, full_text, "api")
            result["saved_path"] = str(saved) if saved else None

        _complete_agent_run_with_tokens(run_id, result, token_summary)
        _create_llm_interaction(run_id, label, prompt, full_text, token_summary, elapsed)

        _broadcast_sync(
            run_id,
            "completed",
            {
                "elapsed_seconds": round(elapsed, 1),
                "run_id": run_id,
                **token_summary,
                "saved_path": result.get("saved_path", ""),
                "canonical_path": result.get("canonical_path", ""),
            },
            seq,
        )

    except Exception as e:
        logger.exception(f"API streaming research failed: {e}")
        _fail_agent_run(run_id, str(e))
        _broadcast_sync(run_id, "failed", {"error": str(e)[:500]}, seq)
    finally:
        _hb_stop_api.set()
        _clear_running()
        # Schedule buffer cleanup
        def _cleanup():
            time.sleep(300)
            from src.web.routes.websocket import cleanup_research_buffer
            cleanup_research_buffer(run_id)

        threading.Thread(target=_cleanup, daemon=True).start()


# ---------------------------------------------------------------------------
# DB helpers for streaming runs
# ---------------------------------------------------------------------------


def _complete_agent_run_with_tokens(run_id: str, result: dict, token_summary: dict) -> None:
    """Update AgentRun with results + token/cost data."""
    try:
        from src.db.database import get_db
        from src.db.models import AgentRun

        content = result.get("content", "")

        with get_db() as session:
            run = session.query(AgentRun).filter(AgentRun.id == run_id).first()
            if run:
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.findings_summary = content
                run.raw_output = content
                run.tokens_used = token_summary.get("total_tokens", 0)
                run.cost_usd = token_summary.get("cost_usd", 0.0)
                # Populate artifacts
                stream_log = STREAM_LOGS_DIR / f"{run_id}.jsonl"
                run.artifacts = json.dumps({
                    "canonical_path": result.get("canonical_path"),
                    "saved_path": result.get("saved_path"),
                    "stream_log_path": str(stream_log) if stream_log.exists() else None,
                })
    except Exception as e:
        logger.warning(f"Failed to complete agent_run with tokens: {e}")

    # Index the output file as a document
    _index_research_document(run_id, result)

    # Create ProcessEvent
    try:
        from src.db.database import get_db
        from src.db.models import ProcessEvent

        with get_db() as session:
            event = ProcessEvent(
                id=f"evt_{run_id}",
                event_type="research_completed",
                source="web_dashboard",
                severity="info",
                title=f"Research: {result.get('label', 'Unknown')}",
                detail=json.dumps({
                    "elapsed": result.get("elapsed_seconds", 0),
                    "mode": result.get("mode", "claude_code"),
                    "saved_path": result.get("saved_path", ""),
                    "canonical_path": result.get("canonical_path", ""),
                    "tokens": token_summary.get("total_tokens", 0),
                    "cost_usd": token_summary.get("cost_usd", 0.0),
                }),
                agent_run_id=run_id,
            )
            session.add(event)
    except Exception as e:
        logger.warning(f"Failed to create process event: {e}")


def _create_llm_interaction(
    run_id: str, label: str, prompt: str, response: str, token_summary: dict, elapsed: float
) -> None:
    """Create an LLMInteraction record for the /llm/ log page."""
    try:
        from src.db.database import get_db
        from src.db.models import LLMInteraction

        interaction_id = f"llm_{run_id}"
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]

        with get_db() as session:
            interaction = LLMInteraction(
                id=interaction_id,
                trigger_type="research",
                trigger_id=run_id,
                model=token_summary.get("model", "unknown"),
                system_prompt_hash=prompt_hash,
                user_prompt=prompt[:5000],
                response=response[:10000],
                tokens_input=token_summary.get("input_tokens", 0),
                tokens_output=token_summary.get("output_tokens", 0),
                cost_usd=token_summary.get("cost_usd", 0.0),
                latency_ms=int(elapsed * 1000),
            )
            session.add(interaction)
    except Exception as e:
        logger.warning(f"Failed to create LLM interaction: {e}")


def _save_stream_log(run_id: str, raw_lines: list[str]) -> Path | None:
    """Write raw stream lines to JSONL file for replay.

    Skips writing if incremental file already exists (written by
    _append_to_stream_log during streaming) to avoid duplicate data.
    """
    try:
        STREAM_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        filepath = STREAM_LOGS_DIR / f"{run_id}.jsonl"
        if filepath.exists() and filepath.stat().st_size > 0:
            return filepath  # incremental writes already populated this
        filepath.write_text("\n".join(raw_lines) + "\n")
        return filepath
    except Exception as e:
        logger.warning(f"Failed to save stream log: {e}")
        return None


def get_run_stream_log(run_id: str) -> list[str] | None:
    """Read a saved JSONL stream log for replay."""
    filepath = STREAM_LOGS_DIR / f"{run_id}.jsonl"
    if filepath.exists():
        return [line for line in filepath.read_text().splitlines() if line.strip()]
    return None


def has_stream_log(run_id: str) -> bool:
    """Check if a stream log exists for a given run."""
    return (STREAM_LOGS_DIR / f"{run_id}.jsonl").exists()
