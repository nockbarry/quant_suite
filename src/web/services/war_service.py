"""War dashboard data service.

Assembles geopolitical monitoring data from existing Athena data sources:
- Oil/commodity prices from state.json
- News items filtered for war keywords from news_cache.json
- Portfolio exposure by conflict thesis from theses
- VIX-based escalation estimation
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Conflict-related thesis name keywords
CONFLICT_THESIS_KEYWORDS = [
    "iran", "war", "defense", "energy supercycle", "hormuz",
    "shipping", "chokepoint", "venezuela", "gold", "de-dollarization",
    "fertilizer", "agflation", "rare earth", "cyber", "european defense",
    "rearm",
]

# War/escalation news keywords
WAR_NEWS_KEYWORDS = [
    "iran", "strike", "attack", "military", "missile", "bomb",
    "war", "conflict", "escalat", "retali", "hormuz", "blockade",
    "sanction", "invasion", "troops", "defense", "weapon", "nuclear",
    "drone", "navy", "airstrike", "casualt",
]

# Diplomatic / de-escalation keywords
DIPLOMATIC_KEYWORDS = [
    "ceasefire", "peace", "negotiate", "diplomat", "mediat", "truce",
    "deal", "talks", "envoy", "summit", "accord", "treaty",
    "de-escalat", "withdrawal", "humanitarian",
]


def get_war_dashboard_data() -> dict:
    """Assemble all war dashboard data from existing sources."""
    return {
        "oil": _get_oil_data(),
        "commodities": _get_commodity_data(),
        "portfolio_exposure": _get_conflict_exposure(),
        "war_news": _get_war_news(),
        "diplomatic_signals": _get_diplomatic_news(),
        "escalation_level": _estimate_escalation(),
        "last_updated": datetime.now().isoformat(),
    }


def _load_state() -> dict:
    """Load state.json safely."""
    state_file = paths.live_state
    if not state_file.exists():
        return {}
    try:
        with open(state_file) as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load state.json: {e}")
        return {}


def _get_oil_data() -> dict:
    """Get oil/energy price data from state.json market section."""
    state = _load_state()
    market = state.get("market", {})

    # Find energy-related positions for proxy pricing
    positions = state.get("positions", [])
    energy_positions = [
        p for p in positions
        if p.get("sector") == "Energy"
    ]

    # SPY/VIX as market context
    result = {
        "spy_price": market.get("spy_price"),
        "spy_change_pct": market.get("spy_change_pct"),
        "vix": market.get("vix"),
        "vix_change_pct": market.get("vix_change_pct"),
        "leading_sectors": market.get("leading_sectors", []),
        "lagging_sectors": market.get("lagging_sectors", []),
        "energy_positions": [
            {
                "symbol": p.get("symbol"),
                "price": p.get("current_price"),
                "day_pnl_pct": p.get("day_pnl_pct"),
                "unrealized_pnl_pct": p.get("unrealized_pnl_pct"),
            }
            for p in energy_positions[:10]
        ],
    }
    return result


def _get_commodity_data() -> dict:
    """Get commodity data from pipeline files if they exist."""
    result = {}
    for name in [
        "fertilizer_prices", "shipping_rates", "lng_prices", "hormuz_status",
    ]:
        path = paths.live / f"{name}.json"
        if path.exists():
            try:
                with open(path) as f:
                    result[name] = json.load(f)
            except Exception:
                pass
    return result


def _get_conflict_exposure() -> list:
    """Calculate portfolio % tied to each conflict thesis."""
    state = _load_state()
    positions = state.get("positions", [])
    theses = state.get("theses", [])
    portfolio = state.get("portfolio", {})
    equity = portfolio.get("equity", 1)  # avoid div by zero

    if not equity or equity <= 0:
        equity = 1

    # Build position lookup: symbol -> market_value
    pos_values = {}
    for p in positions:
        symbol = p.get("symbol", "")
        mv = p.get("market_value", 0) or 0
        pos_values[symbol] = mv

    # Find conflict-related theses
    conflict_theses = []
    for thesis in theses:
        name_lower = thesis.get("name", "").lower()
        is_conflict = any(kw in name_lower for kw in CONFLICT_THESIS_KEYWORDS)
        if not is_conflict:
            continue

        # Sum market value of thesis positions
        thesis_positions = thesis.get("positions", [])
        thesis_value = sum(pos_values.get(sym, 0) for sym in thesis_positions)
        thesis_pct = (thesis_value / equity) * 100 if equity > 0 else 0

        # Get position details
        pos_details = []
        for sym in thesis_positions:
            for p in positions:
                if p.get("symbol") == sym:
                    pos_details.append({
                        "symbol": sym,
                        "pnl_pct": p.get("unrealized_pnl_pct", 0),
                        "value": p.get("market_value", 0),
                    })
                    break

        conflict_theses.append({
            "id": thesis.get("id", ""),
            "name": thesis.get("name", ""),
            "conviction": thesis.get("conviction", 0),
            "status": thesis.get("status", ""),
            "portfolio_pct": round(thesis_pct, 1),
            "total_value": round(thesis_value, 2),
            "position_count": len(thesis_positions),
            "positions": pos_details,
        })

    # Sort by portfolio weight descending
    conflict_theses.sort(key=lambda t: t["portfolio_pct"], reverse=True)
    return conflict_theses


def _load_news_items() -> list:
    """Load news items from news_cache.json."""
    news_file = paths.live / "news_cache.json"
    if not news_file.exists():
        return []
    try:
        with open(news_file) as f:
            data = json.load(f)
        return data.get("items", [])
    except Exception as e:
        logger.warning(f"Could not load news_cache.json: {e}")
        return []


def _get_war_news() -> list:
    """Filter news items for war/conflict keywords."""
    items = _load_news_items()
    filtered = []
    for item in items:
        headline = item.get("headline", "").lower()
        if any(kw in headline for kw in WAR_NEWS_KEYWORDS):
            filtered.append({
                "headline": item.get("headline", ""),
                "timestamp": item.get("timestamp", item.get("pubdate", "")),
                "source": item.get("source", ""),
                "is_urgent": item.get("is_urgent", False),
                "thesis_matches": item.get("thesis_matches", {}),
            })
    return filtered[:30]


def _get_diplomatic_news() -> list:
    """Filter news items for ceasefire/mediation/diplomatic keywords."""
    items = _load_news_items()
    filtered = []
    for item in items:
        headline = item.get("headline", "").lower()
        if any(kw in headline for kw in DIPLOMATIC_KEYWORDS):
            filtered.append({
                "headline": item.get("headline", ""),
                "timestamp": item.get("timestamp", item.get("pubdate", "")),
                "source": item.get("source", ""),
            })
    return filtered[:20]


def _estimate_escalation() -> dict:
    """Rule-based escalation level estimation from VIX and news density.

    Returns level 1-10 with description and color class.
    """
    state = _load_state()
    market = state.get("market", {})
    vix = market.get("vix", 15)

    # Count war news as density signal
    items = _load_news_items()
    war_count = sum(
        1 for item in items
        if any(kw in item.get("headline", "").lower() for kw in WAR_NEWS_KEYWORDS)
    )

    # Base level from VIX
    if vix >= 40:
        level = 9
    elif vix >= 35:
        level = 8
    elif vix >= 30:
        level = 7
    elif vix >= 27:
        level = 6
    elif vix >= 23:
        level = 5
    elif vix >= 20:
        level = 4
    elif vix >= 17:
        level = 3
    elif vix >= 14:
        level = 2
    else:
        level = 1

    # Adjust by news density (up to +1)
    if war_count > 20:
        level = min(level + 1, 10)

    # Description mapping
    descriptions = {
        1: "Calm — no significant geopolitical risk",
        2: "Low — routine tensions, markets stable",
        3: "Elevated — some tension, markets cautious",
        4: "Moderate — active disputes, mild market impact",
        5: "Heightened — active conflict risk, volatility rising",
        6: "High — significant conflict activity, markets stressed",
        7: "Severe — major conflict escalation, high volatility",
        8: "Critical — active military operations, extreme volatility",
        9: "Extreme — full-scale conflict, markets in crisis",
        10: "Maximum — unprecedented escalation",
    }

    # Color class for the template
    if level <= 2:
        color = "emerald"
    elif level <= 4:
        color = "yellow"
    elif level <= 6:
        color = "orange"
    elif level <= 8:
        color = "red"
    else:
        color = "red"

    return {
        "level": level,
        "max_level": 10,
        "description": descriptions.get(level, "Unknown"),
        "color": color,
        "vix": vix,
        "war_news_count": war_count,
    }
