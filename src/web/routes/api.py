"""API routes — JSON health check, state endpoint, and trade approval."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

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
