"""Signals routes — signal provenance list and detail."""

from fastapi import APIRouter, Request, HTTPException

from src.web.services import signal_service

router = APIRouter()


@router.get("/")
async def signal_list(request: Request):
    """Signal list grouped by symbol."""
    templates = request.app.state.templates

    # Parse query filters
    source = request.query_params.get("source")
    symbol = request.query_params.get("symbol")
    direction = request.query_params.get("direction")
    outcome = request.query_params.get("outcome")
    limit = int(request.query_params.get("limit", 100))

    signals = signal_service.list_signals(
        source=source,
        symbol=symbol,
        direction=direction,
        outcome=outcome,
        limit=limit,
    )

    # Group by symbol for the grouped display
    grouped = signal_service.group_by_symbol(signals)

    return templates.TemplateResponse(
        request,
        "signals/index.html",
        {
            "active_page": "signals",
            "signals": signals,
            "signals_by_symbol": grouped,
            "filters": {
                "source": source,
                "symbol": symbol,
                "direction": direction,
                "outcome": outcome,
            },
            "breadcrumbs": [
                {"label": "Signals"},
            ],
        },
    )


@router.get("/{signal_id}")
async def signal_detail(request: Request, signal_id: str):
    """Signal provenance detail with full lifecycle."""
    templates = request.app.state.templates

    signal = signal_service.get_signal(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found")

    # Get decisions that used this signal
    linked_decisions = signal_service.get_signal_decisions(signal_id)

    s_symbol = signal.get("symbol", "") if isinstance(signal, dict) else getattr(signal, "symbol", "")
    s_source = signal.get("source", "") if isinstance(signal, dict) else getattr(signal, "source", "")
    s_label = f"{s_symbol} — {s_source}" if s_symbol else signal_id[:8]

    return templates.TemplateResponse(
        request,
        "signals/detail.html",
        {
            "active_page": "signals",
            "signal": signal,
            "linked_decisions": linked_decisions,
            "breadcrumbs": [
                {"label": "Signals", "url": "/signals"},
                {"label": s_label},
            ],
        },
    )
