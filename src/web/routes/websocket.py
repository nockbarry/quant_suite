"""WebSocket routes — real-time event push and state diffs."""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.web.services import state_service

router = APIRouter()

# Simple connection manager for broadcasting
_event_connections: list[WebSocket] = []
_state_connections: list[WebSocket] = []


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
