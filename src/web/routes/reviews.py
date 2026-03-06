"""Review routes — EOD reviews, internal reviews, and briefings."""

from fastapi import APIRouter, Request

from src.web.services import review_service

router = APIRouter()


@router.get("/")
async def reviews_index(request: Request):
    """Reviews timeline: EOD reviews, internal reviews, briefings."""
    templates = request.app.state.templates

    eod_reviews = review_service.get_eod_reviews(limit=20)
    internal_reviews = review_service.get_internal_reviews(limit=10)
    briefings = review_service.get_briefings(limit=10)

    return templates.TemplateResponse(
        request,
        "reviews/index.html",
        {
            "active_page": "reviews",
            "eod_reviews": eod_reviews,
            "internal_reviews": internal_reviews,
            "briefings": briefings,
        },
    )


@router.get("/eod/{date}")
async def eod_detail(request: Request, date: str):
    """Detail view for a specific EOD review."""
    templates = request.app.state.templates

    review = review_service.get_eod_review(date)
    if not review:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Review not found")

    return templates.TemplateResponse(
        request,
        "reviews/eod_detail.html",
        {
            "active_page": "reviews",
            "review": review,
        },
    )
