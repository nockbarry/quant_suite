"""Knowledge routes — company and sector CRUD."""

from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse

from src.web.services import knowledge_service

router = APIRouter()


@router.get("/")
async def knowledge_list(request: Request):
    """List all companies and sectors."""
    templates = request.app.state.templates

    companies = knowledge_service.list_companies()
    sectors = knowledge_service.list_sectors()

    return templates.TemplateResponse(
        request,
        "knowledge/index.html",
        {
            "active_page": "knowledge",
            "companies": companies,
            "sectors": sectors,
        },
    )


@router.get("/sectors/{name}")
async def sector_detail(request: Request, name: str):
    """Sector detail page."""
    templates = request.app.state.templates

    sector = knowledge_service.get_sector(name)
    if sector is None:
        raise HTTPException(status_code=404, detail=f"Sector '{name}' not found")

    # Get companies in this sector
    all_companies = knowledge_service.list_companies()
    sector_companies = [c for c in all_companies if c.get("sector", "").lower() == name.lower()]

    return templates.TemplateResponse(
        request,
        "knowledge/company.html",
        {
            "active_page": "knowledge",
            "sector": sector,
            "companies": sector_companies,
        },
    )


@router.get("/{symbol}")
async def company_detail(request: Request, symbol: str):
    """Company detail page."""
    templates = request.app.state.templates

    company = knowledge_service.get_company(symbol.upper())
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company '{symbol}' not found")

    return templates.TemplateResponse(
        request,
        "knowledge/company.html",
        {
            "active_page": "knowledge",
            "company": company,
        },
    )


@router.post("/")
async def create_company(
    request: Request,
    symbol: str = Form(...),
    name: str = Form(...),
    sector: str = Form(""),
    business_model: str = Form(""),
    moat: str = Form(""),
    market_cap_tier: str = Form(""),
):
    """Create a new company from form submission."""
    data = {
        "symbol": symbol.upper(),
        "name": name,
        "sector": sector,
        "business_model": business_model,
        "moat": moat,
        "market_cap_tier": market_cap_tier,
    }
    knowledge_service.create_company(data)
    return RedirectResponse(url=f"/knowledge/{symbol.upper()}", status_code=303)


@router.put("/{symbol}")
async def update_company(request: Request, symbol: str):
    """Update an existing company from form data."""
    form = await request.form()
    data = {k: v for k, v in form.items() if k != "symbol"}

    updated = knowledge_service.update_company(symbol.upper(), data)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Company '{symbol}' not found")

    return RedirectResponse(url=f"/knowledge/{symbol.upper()}", status_code=303)


@router.delete("/{symbol}")
async def delete_company(request: Request, symbol: str):
    """Delete a company."""
    deleted = knowledge_service.delete_company(symbol.upper())
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Company '{symbol}' not found")

    return RedirectResponse(url="/knowledge", status_code=303)
