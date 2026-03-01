"""Documents routes — universal document browser."""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from src.web.services import document_service

router = APIRouter()


@router.get("/")
async def document_list(request: Request):
    """Filterable document grid."""
    templates = request.app.state.templates

    doc_type = request.query_params.get("type", "")
    symbol = request.query_params.get("symbol", "")
    search = request.query_params.get("q", "")
    source = request.query_params.get("source", "")

    documents, total = document_service.list_documents(
        doc_type=doc_type or None,
        symbol=symbol or None,
        search=search or None,
        source=source or None,
        limit=100,
    )
    type_counts = document_service.get_doc_type_counts()

    return templates.TemplateResponse(
        request,
        "documents/index.html",
        {
            "active_page": "documents",
            "documents": documents,
            "total": total,
            "type_counts": type_counts,
            "filter_type": doc_type,
            "filter_symbol": symbol,
            "filter_search": search,
            "filter_source": source,
        },
    )


@router.get("/{doc_id}")
async def document_detail(request: Request, doc_id: str):
    """View a single document with full content."""
    templates = request.app.state.templates

    doc = document_service.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found")

    return templates.TemplateResponse(
        request,
        "documents/view.html",
        {
            "active_page": "documents",
            "doc": doc,
            "breadcrumbs": [
                {"label": "Documents", "url": "/documents"},
                {"label": doc["title"][:60]},
            ],
        },
    )


@router.get("/insights/list")
async def insight_list(request: Request):
    """Browse research insights."""
    templates = request.app.state.templates

    category = request.query_params.get("category", "")
    search = request.query_params.get("q", "")
    validated = request.query_params.get("validated", "") == "true"

    insights = document_service.list_insights(
        category=category or None,
        search=search or None,
        validated_only=validated,
    )
    categories = document_service.get_insight_categories()

    return templates.TemplateResponse(
        request,
        "documents/insights.html",
        {
            "active_page": "documents",
            "insights": insights,
            "categories": categories,
            "filter_category": category,
            "filter_search": search,
            "filter_validated": validated,
        },
    )


@router.get("/experiments/list")
async def experiment_list(request: Request):
    """Browse research experiments."""
    templates = request.app.state.templates

    strategy = request.query_params.get("strategy", "")
    symbol = request.query_params.get("symbol", "")

    experiments = document_service.list_experiments(
        strategy=strategy or None,
        symbol=symbol or None,
    )

    return templates.TemplateResponse(
        request,
        "documents/experiments.html",
        {
            "active_page": "documents",
            "experiments": experiments,
            "filter_strategy": strategy,
            "filter_symbol": symbol,
        },
    )
