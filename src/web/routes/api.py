"""API routes — JSON health check, state endpoint, search, and trade approval."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse

from src.web.services import state_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """JSON health check for monitoring and sidebar status dot."""
    state_age = state_service.get_state_age_seconds()

    if state_age < 0:
        status = "degraded"
        detail = "state.json not found"
    elif state_age > 1800:
        status = "degraded"
        detail = f"state.json is {state_age}s old"
    else:
        status = "healthy"
        detail = "all systems operational"

    return JSONResponse(
        content={
            "status": status,
            "detail": detail,
            "state_age_seconds": state_age,
        }
    )


@router.get("/state")
async def get_state():
    """Return current state.json contents."""
    state = state_service.get_live_state()
    return JSONResponse(content=state)


@router.post("/trades/approve/{trade_id}")
async def approve_trade(trade_id: str):
    """Approve a queued trade by updating its decision status."""
    from src.web.services import decision_service

    result = decision_service.update_decision_status(trade_id, "approved")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Trade '{trade_id}' not found")

    return JSONResponse(
        content={
            "status": "approved",
            "trade_id": trade_id,
            "message": f"Trade {trade_id} approved for execution",
        }
    )


@router.post("/trades/reject/{trade_id}")
async def reject_trade(trade_id: str):
    """Reject a queued trade by updating its decision status."""
    from src.web.services import decision_service

    result = decision_service.update_decision_status(trade_id, "rejected")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Trade '{trade_id}' not found")

    return JSONResponse(
        content={
            "status": "rejected",
            "trade_id": trade_id,
            "message": f"Trade {trade_id} rejected",
        }
    )


@router.get("/search")
async def global_search(request: Request):
    """Global search across companies, theses, decisions, signals. Returns HTML dropdown."""
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        return HTMLResponse("")

    from src.db.database import get_db
    from src.db.models import (
        Company, ThesisRecord, DecisionRecord,
        SignalProvenanceRecord, ThesisPositionLink,
    )

    results = []
    q_upper = q.upper()
    q_like = f"%{q}%"

    try:
        with get_db() as session:
            # Companies
            companies = (
                session.query(Company)
                .filter(Company.symbol.like(q_like))
                .limit(5)
                .all()
            )
            for c in companies:
                results.append({
                    "category": "Company",
                    "label": f"{c.symbol} — {c.name}",
                    "url": f"/knowledge/{c.symbol}",
                })

            # Theses — by name or by position symbol
            theses = (
                session.query(ThesisRecord)
                .filter(ThesisRecord.name.ilike(q_like))
                .limit(5)
                .all()
            )
            for t in theses:
                results.append({
                    "category": "Thesis",
                    "label": t.name,
                    "url": f"/theses/{t.id}",
                })

            # Theses by position link
            linked_thesis_ids = (
                session.query(ThesisPositionLink.thesis_id)
                .filter(ThesisPositionLink.symbol == q_upper)
                .distinct()
                .limit(5)
                .all()
            )
            for (tid,) in linked_thesis_ids:
                t = session.query(ThesisRecord).filter(ThesisRecord.id == tid).first()
                if t and not any(r["url"] == f"/theses/{t.id}" for r in results):
                    results.append({
                        "category": "Thesis",
                        "label": f"{t.name} (has {q_upper})",
                        "url": f"/theses/{t.id}",
                    })

            # Decisions
            decisions = (
                session.query(DecisionRecord)
                .filter(DecisionRecord.symbol == q_upper)
                .order_by(DecisionRecord.timestamp.desc())
                .limit(5)
                .all()
            )
            for d in decisions:
                ts = d.timestamp.strftime("%m/%d") if d.timestamp else ""
                results.append({
                    "category": "Decision",
                    "label": f"{d.symbol} {d.action} ({ts})",
                    "url": f"/decisions/{d.id}",
                })

            # Signals
            signals = (
                session.query(SignalProvenanceRecord)
                .filter(SignalProvenanceRecord.symbol == q_upper)
                .order_by(SignalProvenanceRecord.first_detected.desc())
                .limit(3)
                .all()
            )
            for s in signals:
                results.append({
                    "category": "Signal",
                    "label": f"{s.symbol} — {s.source} ({s.initial_direction})",
                    "url": f"/signals/{s.signal_id}",
                })

    except Exception:
        pass

    if not results:
        return HTMLResponse(
            '<div class="px-4 py-3 text-xs text-gray-500">No results</div>'
        )

    html_parts = []
    current_cat = None
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            html_parts.append(
                f'<div class="px-3 py-1 text-[10px] text-gray-500 uppercase bg-gray-900">{current_cat}</div>'
            )
        html_parts.append(
            f'<a href="{r["url"]}" class="block px-4 py-2 text-xs text-gray-300 hover:bg-gray-700 hover:text-emerald-400 transition">'
            f'{r["label"]}</a>'
        )

    return HTMLResponse("\n".join(html_parts))
