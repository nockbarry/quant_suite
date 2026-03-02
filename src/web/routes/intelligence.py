"""Intelligence dashboard routes — prediction tracking, calibration, setup types."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


@router.get("/", response_class=HTMLResponse)
async def intelligence_dashboard(request: Request):
    """Main intelligence dashboard."""
    from src.web.services.intelligence_service import (
        get_intelligence_summary,
        get_prediction_scorecard,
        get_setup_type_performance,
        get_calibration_data,
        get_signal_quality_leaderboard,
        list_predictions,
    )

    summary = get_intelligence_summary()
    scorecard = get_prediction_scorecard()
    setup_types = get_setup_type_performance()
    calibration = get_calibration_data()
    signal_quality = get_signal_quality_leaderboard()
    recent_predictions = list_predictions(limit=20)

    return _templates(request).TemplateResponse(
        "intelligence/index.html",
        {
            "request": request,
            "active_page": "intelligence",
            "summary": summary,
            "scorecard": scorecard,
            "setup_types": setup_types,
            "calibration": calibration,
            "signal_quality": signal_quality,
            "recent_predictions": recent_predictions,
        },
    )


@router.get("/predictions", response_class=HTMLResponse)
async def predictions_list(
    request: Request,
    symbol: str = "",
    status: str = "",
    prediction_type: str = "",
    limit: int = 50,
):
    """Prediction list with filters."""
    from src.web.services.intelligence_service import (
        list_predictions,
        get_distinct_prediction_types,
        get_distinct_prediction_statuses,
    )

    predictions = list_predictions(
        limit=limit,
        symbol=symbol or None,
        status=status or None,
        prediction_type=prediction_type or None,
    )
    prediction_types = get_distinct_prediction_types()
    statuses = get_distinct_prediction_statuses()

    return _templates(request).TemplateResponse(
        "intelligence/predictions.html",
        {
            "request": request,
            "active_page": "intelligence",
            "predictions": predictions,
            "prediction_types": prediction_types,
            "statuses": statuses,
            "filter_symbol": symbol,
            "filter_status": status,
            "filter_type": prediction_type,
        },
    )


@router.get("/predictions/{pred_id}", response_class=HTMLResponse)
async def prediction_detail(request: Request, pred_id: str):
    """Prediction detail with resolution timeline."""
    from src.web.services.intelligence_service import get_prediction
    from fastapi.responses import RedirectResponse

    prediction = get_prediction(pred_id)
    if not prediction:
        return RedirectResponse("/intelligence/predictions")

    return _templates(request).TemplateResponse(
        "intelligence/detail.html",
        {
            "request": request,
            "active_page": "intelligence",
            "prediction": prediction,
        },
    )


@router.get("/context/{symbol}", response_class=HTMLResponse)
async def context_partial(request: Request, symbol: str):
    """Decision context for a symbol — works as both page and HTMX partial."""
    from src.intelligence.context_builder import DecisionContextBuilder

    builder = DecisionContextBuilder()
    ctx = builder.build_context(symbol.upper())

    return _templates(request).TemplateResponse(
        "intelligence/context_partial.html",
        {
            "request": request,
            "active_page": "intelligence",
            "symbol": symbol.upper(),
            "context": ctx,
            "summary_text": ctx.summary,
        },
    )


@router.get("/calibration", response_class=HTMLResponse)
async def calibration_partial(request: Request):
    """HTMX partial: calibration chart data."""
    from src.web.services.intelligence_service import get_calibration_data
    import json

    calibration = get_calibration_data()
    return HTMLResponse(
        content=json.dumps(calibration),
        media_type="application/json",
    )


@router.get("/setup-types", response_class=HTMLResponse)
async def setup_types_partial(request: Request):
    """HTMX partial: setup type performance."""
    from src.web.services.intelligence_service import get_setup_type_performance
    import json

    setup_types = get_setup_type_performance()
    return HTMLResponse(
        content=json.dumps(setup_types),
        media_type="application/json",
    )
