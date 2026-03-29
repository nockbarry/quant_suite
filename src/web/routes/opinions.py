"""Web routes for the Market Opinion System."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def opinions_dashboard(request: Request):
    """Main opinions dashboard."""
    from src.web.services import opinion_service

    scorecard = opinion_service.get_opinion_scorecard()
    calibration = opinion_service.get_opinion_calibration()
    recent = opinion_service.list_opinions(limit=20)
    quality = opinion_service.get_decision_quality_summary()

    # Build simple HTML dashboard
    html = _build_dashboard_html(scorecard, calibration, recent, quality)
    return HTMLResponse(content=html)


@router.get("/quality", response_class=HTMLResponse)
async def quality_dashboard(request: Request):
    """Decision quality curves per instance."""
    from src.web.services import opinion_service

    curves = opinion_service.get_decision_quality_curves()
    html = _build_quality_html(curves)
    return HTMLResponse(content=html)


@router.get("/divergence", response_class=HTMLResponse)
async def divergence_dashboard(request: Request):
    """Cross-instance opinion divergence."""
    from src.web.services import opinion_service

    divergence = opinion_service.get_opinion_divergence()
    html = _build_divergence_html(divergence)
    return HTMLResponse(content=html)


@router.get("/symbol/{symbol}", response_class=HTMLResponse)
async def symbol_history(request: Request, symbol: str):
    """Opinion history for one symbol."""
    from src.web.services import opinion_service

    opinions = opinion_service.get_symbol_opinion_history(symbol)
    html = _build_symbol_html(symbol, opinions)
    return HTMLResponse(content=html)


@router.get("/api/scorecard", response_class=JSONResponse)
async def api_scorecard(instance_id: str = None):
    """JSON API for scorecard data."""
    from src.web.services import opinion_service
    return opinion_service.get_opinion_scorecard(instance_id)


@router.get("/api/calibration", response_class=JSONResponse)
async def api_calibration():
    """JSON API for calibration data."""
    from src.web.services import opinion_service
    return opinion_service.get_opinion_calibration()


@router.get("/api/quality", response_class=JSONResponse)
async def api_quality():
    """JSON API for decision quality data."""
    from src.web.services import opinion_service
    return opinion_service.get_decision_quality_curves()


@router.get("/api/divergence", response_class=JSONResponse)
async def api_divergence():
    """JSON API for divergence data."""
    from src.web.services import opinion_service
    return opinion_service.get_opinion_divergence()


# --- HTML builders (minimal, dark-themed) ---

def _page_wrapper(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><title>{title} — Athena Opinions</title>
<style>
body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Courier New', monospace; margin: 20px; }}
h1, h2 {{ color: #00d4ff; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th, td {{ padding: 6px 12px; text-align: left; border-bottom: 1px solid #333; }}
th {{ background: #16213e; color: #00d4ff; }}
tr:hover {{ background: #16213e; }}
.good {{ color: #00ff88; }} .bad {{ color: #ff4444; }} .neutral {{ color: #888; }}
a {{ color: #00d4ff; text-decoration: none; }} a:hover {{ text-decoration: underline; }}
nav {{ margin-bottom: 20px; }} nav a {{ margin-right: 15px; }}
.card {{ background: #16213e; padding: 15px; border-radius: 8px; margin: 10px 0; }}
</style></head><body>
<nav><a href="/opinions/">Dashboard</a> <a href="/opinions/quality">Quality</a> <a href="/opinions/divergence">Divergence</a></nav>
<h1>{title}</h1>
{body}
</body></html>"""


def _build_dashboard_html(scorecard: dict, calibration: dict, recent: list, quality: dict) -> str:
    body = '<div class="card"><h2>Opinion Scorecard</h2>'
    if scorecard.get("total_scored", 0) == 0:
        body += "<p>No scored opinions yet. Opinions will be scored after 5+ days of capture.</p>"
    else:
        body += f"<p>Total scored: {scorecard['total_scored']}</p><table><tr><th>Horizon</th><th>Direction Acc</th><th>Range Acc</th><th>Avg Proximity</th><th>n</th></tr>"
        for h in ("5d", "10d", "30d"):
            d = scorecard.get(h, {})
            if d:
                dir_cls = "good" if d["direction_accuracy"] > 0.5 else "bad"
                body += f'<tr><td>{h}</td><td class="{dir_cls}">{d["direction_accuracy"]:.1%}</td><td>{d["range_accuracy"]:.1%}</td><td>{d["avg_proximity"]:.1%}</td><td>{d["count"]}</td></tr>'
        body += "</table>"
    body += "</div>"

    body += '<div class="card"><h2>Calibration</h2>'
    bins = calibration.get("bins", [])
    if bins:
        cal_err = calibration.get("calibration_error")
        body += f"<p>Calibration error: <b>{cal_err:.3f}</b></p>" if cal_err else ""
        body += "<table><tr><th>Confidence</th><th>Predicted</th><th>Actual Dir</th><th>Actual Range</th><th>n</th></tr>"
        for b in bins:
            body += f'<tr><td>{b["label"]}</td><td>{b["predicted_confidence"]:.1%}</td><td>{b["actual_direction_rate"]:.1%}</td><td>{b["actual_range_rate"]:.1%}</td><td>{b["count"]}</td></tr>'
        body += "</table>"
    else:
        body += "<p>No calibration data yet.</p>"
    body += "</div>"

    body += '<div class="card"><h2>Decision Quality</h2>'
    if quality.get("total", 0) > 0:
        body += f"<p>Total decisions tracked: {quality['total']}</p><table><tr><th>Horizon</th><th>Avg Quality</th><th>Avg Return</th><th>Alpha vs SPY</th><th>n</th></tr>"
        for h in ("1d", "5d", "10d", "30d"):
            d = quality.get(h, {})
            if d:
                q_cls = "good" if d["avg_quality"] > 0.5 else "bad"
                body += f'<tr><td>{h}</td><td class="{q_cls}">{d["avg_quality"]:.1%}</td><td>{d["avg_return"]:+.1f}%</td><td>{d["avg_alpha"]:+.1f}%</td><td>{d["count"]}</td></tr>'
        body += "</table>"
    else:
        body += "<p>No decision quality data yet.</p>"
    body += "</div>"

    body += '<div class="card"><h2>Recent Opinions</h2>'
    if recent:
        body += "<table><tr><th>Time</th><th>Symbol</th><th>Dir</th><th>Conf</th><th>5d Base</th><th>10d Base</th><th>Rel</th><th>Driver</th></tr>"
        for o in recent[:20]:
            created = str(o.get("created", ""))[:16]
            dir_cls = "good" if o.get("trend_direction") == "bullish" else ("bad" if o.get("trend_direction") == "bearish" else "neutral")
            body += f'<tr><td>{created}</td><td><a href="/opinions/symbol/{o["symbol"]}">{o["symbol"]}</a></td><td class="{dir_cls}">{o.get("trend_direction","")}</td><td>{o.get("trend_confidence",0):.0%}</td><td>${o.get("target_5d_base",0):.0f}</td><td>${o.get("target_10d_base",0):.0f}</td><td>{o.get("relative_direction","")}</td><td>{o.get("key_driver","")[:30]}</td></tr>'
        body += "</table>"
    else:
        body += "<p>No opinions captured yet.</p>"
    body += "</div>"

    return _page_wrapper("Market Opinions", body)


def _build_quality_html(curves: dict) -> str:
    summary = curves.get("summary", {})
    body = '<div class="card"><h2>Decision Quality Summary</h2>'
    if summary.get("total", 0) > 0:
        body += f"<p>Total decisions: {summary['total']}</p>"
        for h in ("1d", "5d", "10d", "30d"):
            d = summary.get(h, {})
            if d:
                body += f"<p>{h}: quality={d['avg_quality']:.1%}, return={d['avg_return']:+.1f}%, alpha={d['avg_alpha']:+.1f}% (n={d['count']})</p>"
    body += "</div>"

    for instance in ("auto", "beta", "gamma"):
        curve = curves.get(instance, [])
        if curve:
            body += f'<div class="card"><h2>{instance.upper()} Quality Curve</h2>'
            body += "<table><tr><th>Date</th><th>Symbol</th><th>Action</th><th>Quality</th><th>Cum Avg</th></tr>"
            for pt in curve[-20:]:
                q_cls = "good" if pt["quality"] > 0.5 else "bad"
                body += f'<tr><td>{pt["date"]}</td><td>{pt["symbol"]}</td><td>{pt["action"]}</td><td class="{q_cls}">{pt["quality"]:.0f}</td><td>{pt["cumulative_avg"]:.1%}</td></tr>'
            body += "</table></div>"

    return _page_wrapper("Decision Quality", body)


def _build_divergence_html(divergence: dict) -> str:
    body = '<div class="card"><h2>Cross-Instance Opinion Divergence</h2>'
    if not divergence:
        body += "<p>No divergence data yet. Opinions must be captured by 2+ instances on the same symbols.</p></div>"
        return _page_wrapper("Opinion Divergence", body)

    body += f"<p>Symbols compared: {divergence.get('symbol_count', 0)}</p>"
    body += f"<p>Avg direction agreement: {divergence.get('avg_direction_agreement', 0):.1%}</p>"

    high_div = divergence.get("high_divergence", [])
    if high_div:
        body += f'<p class="bad">High divergence: {", ".join(high_div)}</p>'

    high_con = divergence.get("high_consensus", [])
    if high_con:
        body += f'<p class="good">Full consensus: {", ".join(high_con[:10])}</p>'

    per_symbol = divergence.get("per_symbol", {})
    if per_symbol:
        body += "<table><tr><th>Symbol</th><th>Dir Agreement</th><th>Consensus</th><th>10d Target Spread</th><th>Rel Agreement</th><th>Instances</th></tr>"
        for sym, d in sorted(per_symbol.items(), key=lambda x: x[1]["direction_agreement"]):
            cls = "good" if d["direction_agreement"] >= 0.67 else ("bad" if d["direction_agreement"] < 0.5 else "neutral")
            body += f'<tr><td><a href="/opinions/symbol/{sym}">{sym}</a></td><td class="{cls}">{d["direction_agreement"]:.0%}</td><td>{d["consensus_direction"]}</td><td>${d["target_10d_spread"]:.1f}</td><td>{d.get("relative_agreement","")}</td><td>{", ".join(d["instances_with_opinion"])}</td></tr>'
        body += "</table>"

    body += "</div>"
    return _page_wrapper("Opinion Divergence", body)


def _build_symbol_html(symbol: str, opinions: list) -> str:
    body = f'<div class="card"><h2>{symbol} Opinion History ({len(opinions)} records)</h2>'
    if not opinions:
        body += "<p>No opinions for this symbol.</p></div>"
        return _page_wrapper(f"{symbol} Opinions", body)

    body += "<table><tr><th>Time</th><th>Instance</th><th>Dir</th><th>Conf</th><th>Price</th><th>5d B/b/B</th><th>10d B/b/B</th><th>Rel</th><th>Score 5d</th><th>Score 10d</th><th>Driver</th></tr>"
    for o in opinions:
        created = str(o.get("created", ""))[:16]
        dir_cls = "good" if o.get("trend_direction") == "bullish" else ("bad" if o.get("trend_direction") == "bearish" else "neutral")
        s5d = f'{o.get("score_5d_direction","")}'
        s10d = f'{o.get("score_10d_direction","")}'
        body += f'<tr><td>{created}</td><td>{o.get("instance_id","")}</td><td class="{dir_cls}">{o.get("trend_direction","")}</td><td>{o.get("trend_confidence",0):.0%}</td><td>${o.get("price_at_opinion",0):.1f}</td><td>{o.get("target_5d_bear",0):.0f}/{o.get("target_5d_base",0):.0f}/{o.get("target_5d_bull",0):.0f}</td><td>{o.get("target_10d_bear",0):.0f}/{o.get("target_10d_base",0):.0f}/{o.get("target_10d_bull",0):.0f}</td><td>{o.get("relative_direction","")}</td><td>{s5d if s5d != "None" else "-"}</td><td>{s10d if s10d != "None" else "-"}</td><td>{o.get("key_driver","")[:25]}</td></tr>'
    body += "</table></div>"

    return _page_wrapper(f"{symbol} Opinions", body)
