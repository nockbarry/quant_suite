"""WebSocket routes — real-time event push, state diffs, and research streaming."""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.web.services import state_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Simple connection manager for broadcasting
_event_connections: list[WebSocket] = []
_state_connections: list[WebSocket] = []

# ---------------------------------------------------------------------------
# Per-run research streaming
# ---------------------------------------------------------------------------

_research_connections: dict[str, list[WebSocket]] = {}
_research_buffers: dict[str, list[dict]] = {}  # ring buffer per run (max 500)
_BUFFER_MAX = 500

# Event loop captured at startup so background threads can schedule coroutines
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Capture the main asyncio event loop (called from app lifespan)."""
    global _main_loop
    _main_loop = loop


# ---------------------------------------------------------------------------
# Global event broadcast (existing)
# ---------------------------------------------------------------------------


async def broadcast_event(event: dict) -> None:
    """Broadcast a process event to all connected /ws/events clients.

    Call this from any part of the application when a new ProcessEvent is created.
    """
    dead = []
    for ws in _event_connections:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _event_connections.remove(ws)


# ---------------------------------------------------------------------------
# Research stream broadcast
# ---------------------------------------------------------------------------


async def broadcast_research_event(run_id: str, message: dict) -> None:
    """Broadcast a research stream event to all clients watching this run.

    Also emits started/completed/failed to the global /ws/events channel.
    """
    # Buffer for late-join replay
    buf = _research_buffers.setdefault(run_id, [])
    buf.append(message)
    if len(buf) > _BUFFER_MAX:
        del buf[: len(buf) - _BUFFER_MAX]

    # Send to per-run clients
    clients = _research_connections.get(run_id, [])
    dead = []
    for ws in clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in clients:
            clients.remove(ws)

    # Emit key events to global channel
    event_type = message.get("event", "")
    if event_type in ("started", "completed", "failed"):
        await broadcast_event({
            "type": "research_stream",
            "run_id": run_id,
            "event": event_type,
            "data": message.get("data", {}),
            "timestamp": message.get("timestamp", datetime.utcnow().isoformat()),
        })


def broadcast_research_event_sync(run_id: str, message: dict) -> None:
    """Thread-safe wrapper to broadcast from a background thread."""
    if _main_loop is None or _main_loop.is_closed():
        logger.warning("No event loop available for broadcast")
        return
    try:
        future = asyncio.run_coroutine_threadsafe(
            broadcast_research_event(run_id, message), _main_loop
        )
        # Don't block indefinitely — 5s timeout
        future.result(timeout=5)
    except Exception as e:
        logger.debug(f"Broadcast failed for {run_id}: {e}")


def cleanup_research_buffer(run_id: str) -> None:
    """Remove buffer after run completes (called after a delay)."""
    _research_buffers.pop(run_id, None)
    # Also clean up empty connection lists
    conns = _research_connections.get(run_id, [])
    if not conns:
        _research_connections.pop(run_id, None)


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    """Push new ProcessEvents in real-time to connected clients."""
    await websocket.accept()
    _event_connections.append(websocket)
    try:
        # Keep connection alive; client may send pings
        while True:
            # Wait for client messages (pings, close)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _event_connections:
            _event_connections.remove(websocket)


@router.websocket("/ws/state")
async def ws_state(websocket: WebSocket):
    """Push state diffs every 30 seconds."""
    await websocket.accept()
    _state_connections.append(websocket)

    previous_state = None

    try:
        while True:
            current_state = state_service.get_live_state()
            state_age = state_service.get_state_age_seconds()

            # Compute a lightweight diff
            diff = _compute_state_diff(previous_state, current_state)
            previous_state = current_state

            payload = {
                "type": "state_update",
                "timestamp": datetime.utcnow().isoformat(),
                "state_age_seconds": state_age,
                "diff": diff,
                "portfolio_summary": state_service.get_portfolio_summary(current_state),
            }

            await websocket.send_json(payload)

            # Wait 30 seconds before next push
            await asyncio.sleep(30)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in _state_connections:
            _state_connections.remove(websocket)


@router.websocket("/ws/research/{run_id}")
async def ws_research(websocket: WebSocket, run_id: str):
    """Stream research events for a specific run.

    On connect: replay buffered messages, then listen for pings.
    """
    await websocket.accept()

    # Register client
    clients = _research_connections.setdefault(run_id, [])
    clients.append(websocket)

    try:
        # Replay buffered messages for late-join
        buf = _research_buffers.get(run_id, [])
        for msg in buf:
            await websocket.send_json(msg)

        # Keep alive
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if run_id in _research_connections:
            conns = _research_connections[run_id]
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                _research_connections.pop(run_id, None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_state_diff(old: dict | None, new: dict) -> dict:
    """Compute a simple diff between two state snapshots."""
    if old is None:
        return {"type": "full", "changed_keys": list(new.keys())}

    changed = {}
    all_keys = set(list(old.keys()) + list(new.keys()))

    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            changed[key] = {
                "old_summary": _summarize(old_val),
                "new_summary": _summarize(new_val),
            }

    return {
        "type": "diff" if changed else "no_change",
        "changed_keys": list(changed.keys()),
        "changes": changed,
    }


def _summarize(value) -> str:
    """Create a short summary of a value for diff display."""
    if value is None:
        return "null"
    if isinstance(value, (str, int, float, bool)):
        s = str(value)
        return s[:100] + "..." if len(s) > 100 else s
    if isinstance(value, list):
        return f"[{len(value)} items]"
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    return str(type(value).__name__)
