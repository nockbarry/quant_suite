"""Portfolio routes — dual-account view (paper + live) with positions and orders."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.web.services import portfolio_service

router = APIRouter()


@router.get("/")
async def portfolio_index(request: Request):
    """Portfolio overview showing both paper and live accounts."""
    templates = request.app.state.templates

    data = await portfolio_service.fetch_both_accounts()

    return templates.TemplateResponse(
        request,
        "portfolio/index.html",
        {
            "active_page": "portfolio",
            "paper": data["paper"],
            "live": data["live"],
            "fetched_at": data["fetched_at"],
            "breadcrumbs": [
                {"label": "Portfolio"},
            ],
        },
    )


@router.get("/paper")
async def portfolio_paper_partial(request: Request):
    """HTMX partial: refresh paper account data."""
    data = await portfolio_service.fetch_single_account(paper=True)
    return HTMLResponse(_render_account_card(data))


@router.get("/live")
async def portfolio_live_partial(request: Request):
    """HTMX partial: refresh live account data."""
    data = await portfolio_service.fetch_single_account(paper=False)
    return HTMLResponse(_render_account_card(data))


def _render_account_card(data: dict) -> str:
    """Render an account card as HTML partial."""
    label = data.get("label", "Account")
    is_paper = data.get("is_paper", True)
    badge_cls = "bg-yellow-900/50 text-yellow-400" if is_paper else "bg-emerald-900/50 text-emerald-400"

    if data.get("disabled"):
        return f'''
        <div class="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center">
            <span class="px-2 py-0.5 text-[10px] rounded-full {badge_cls}">{label}</span>
            <p class="text-gray-500 text-sm mt-3">Not configured</p>
            <p class="text-gray-600 text-xs mt-1">Set <code class="mono text-gray-500">live_trading_enabled: true</code> in credentials.yaml</p>
        </div>
        '''

    if data.get("error"):
        return f'''
        <div class="bg-gray-900 border border-red-900/50 rounded-lg p-6 text-center">
            <span class="px-2 py-0.5 text-[10px] rounded-full {badge_cls}">{label}</span>
            <p class="text-red-400 text-sm mt-3">Connection Error</p>
            <p class="text-gray-600 text-xs mt-1 mono">{data["error"][:100]}</p>
        </div>
        '''

    account = data.get("account", {}) or {}
    positions = data.get("positions", [])
    orders = data.get("orders", [])
    total_pnl = data.get("total_pnl", 0)
    total_pnl_pct = data.get("total_pnl_pct", 0)

    pnl_cls = "text-profit" if total_pnl >= 0 else "text-loss"

    # Metrics row
    equity = account.get("equity", 0)
    cash = account.get("cash", 0)
    buying_power = account.get("buying_power", 0)
    dt_count = account.get("day_trade_count", 0)

    # Position rows
    pos_rows = []
    for p in positions:
        sym = p["symbol"]
        qty = p["quantity"]
        price = p["current_price"]
        mv = p["market_value"]
        pnl = p["unrealized_pnl"]
        pnl_pct = p["unrealized_pnl_pct"]
        row_pnl_cls = "text-profit" if pnl >= 0 else "text-loss"
        pos_rows.append(f'''
        <tr class="border-b border-gray-800/50 hover:bg-gray-800/30">
            <td class="px-3 py-1.5 mono text-xs"><a href="/knowledge/{sym}" class="text-emerald-400 hover:underline">{sym}</a></td>
            <td class="px-3 py-1.5 text-right mono text-xs">{qty:.0f}</td>
            <td class="px-3 py-1.5 text-right mono text-xs">${price:.2f}</td>
            <td class="px-3 py-1.5 text-right mono text-xs">${mv:.0f}</td>
            <td class="px-3 py-1.5 text-right mono text-xs {row_pnl_cls}">{pnl:+.0f}</td>
            <td class="px-3 py-1.5 text-right mono text-xs {row_pnl_cls}">{pnl_pct:+.1f}%</td>
        </tr>
        ''')

    if not pos_rows:
        pos_rows.append('<tr><td colspan="6" class="px-3 py-6 text-center text-gray-600 text-xs">No positions</td></tr>')

    # Order rows
    order_rows = []
    for o in orders:
        side_cls = "text-emerald-400" if o["side"].lower() == "buy" else "text-red-400"
        order_rows.append(f'''
        <tr class="border-b border-gray-800/50">
            <td class="px-3 py-1.5 mono text-xs">{o["symbol"]}</td>
            <td class="px-3 py-1.5 text-xs {side_cls}">{o["side"].upper()}</td>
            <td class="px-3 py-1.5 text-right mono text-xs">{o["quantity"]:.0f}</td>
            <td class="px-3 py-1.5 text-xs">{o["order_type"]}</td>
            <td class="px-3 py-1.5 text-xs text-gray-500">{o["status"]}</td>
        </tr>
        ''')

    orders_section = ""
    if order_rows:
        orders_section = f'''
        <div class="mt-3 border-t border-gray-800 pt-3">
            <p class="text-[10px] text-gray-500 uppercase mb-2 px-3">Open Orders ({len(orders)})</p>
            <table class="w-full text-xs">
                <thead><tr class="text-[10px] text-gray-600 uppercase">
                    <th class="px-3 py-1 text-left">Symbol</th>
                    <th class="px-3 py-1 text-left">Side</th>
                    <th class="px-3 py-1 text-right">Qty</th>
                    <th class="px-3 py-1 text-left">Type</th>
                    <th class="px-3 py-1 text-left">Status</th>
                </tr></thead>
                <tbody>{"".join(order_rows)}</tbody>
            </table>
        </div>
        '''

    return f'''
    <div class="bg-gray-900 border border-gray-800 rounded-lg">
        <div class="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
            <div class="flex items-center gap-2">
                <span class="px-2 py-0.5 text-[10px] rounded-full {badge_cls}">{label}</span>
                <span class="text-sm font-semibold text-gray-300">${equity:,.0f}</span>
                <span class="text-xs mono {pnl_cls}">{total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)</span>
            </div>
            <span class="text-[10px] text-gray-600">{len(positions)} positions</span>
        </div>
        <div class="grid grid-cols-3 gap-3 px-4 py-2 border-b border-gray-800/50">
            <div>
                <p class="text-[10px] text-gray-600">Cash</p>
                <p class="text-xs mono">${cash:,.0f}</p>
            </div>
            <div>
                <p class="text-[10px] text-gray-600">Buying Power</p>
                <p class="text-xs mono">${buying_power:,.0f}</p>
            </div>
            <div>
                <p class="text-[10px] text-gray-600">Day Trades</p>
                <p class="text-xs mono">{dt_count}/3</p>
            </div>
        </div>
        <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="w-full">
                <thead class="sticky top-0 bg-gray-900">
                    <tr class="text-[10px] text-gray-600 uppercase border-b border-gray-800">
                        <th class="px-3 py-1.5 text-left">Symbol</th>
                        <th class="px-3 py-1.5 text-right">Qty</th>
                        <th class="px-3 py-1.5 text-right">Price</th>
                        <th class="px-3 py-1.5 text-right">Value</th>
                        <th class="px-3 py-1.5 text-right">P&L</th>
                        <th class="px-3 py-1.5 text-right">P&L %</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(pos_rows)}
                </tbody>
            </table>
        </div>
        {orders_section}
    </div>
    '''
