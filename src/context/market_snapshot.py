"""
Market snapshot helper — captures current market state from state.json.

Usage:
    from src.context.market_snapshot import capture_market_snapshot
    snapshot = capture_market_snapshot()
    # Returns a dict with SPY, VIX, sector ETFs, portfolio summary
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

logger = logging.getLogger(__name__)

# Sector ETFs to capture
SECTOR_ETFS = ["XLE", "XLF", "XLK", "XLV", "XLI", "XLC", "XLU", "XLP", "XLY", "XLB", "XLRE"]


def capture_market_snapshot() -> dict:
    """Read current market state from state.json and return a snapshot dict.

    Returns a dict with:
        - timestamp
        - spy_price, spy_change_pct
        - vix, vix_change_pct
        - sector_etfs: {XLE: {...}, ...}
        - portfolio_equity, portfolio_day_pnl_pct, portfolio_cash
        - market_regime, market_trend
    """
    state = _load_state()
    if not state:
        return {"timestamp": datetime.utcnow().isoformat(), "error": "state.json not available"}

    market = state.get("market", {})
    portfolio = state.get("portfolio", {})
    positions = state.get("positions", [])

    # Build sector ETF prices from positions if available
    sector_prices = {}
    for pos in positions:
        sym = pos.get("symbol", "")
        if sym in SECTOR_ETFS:
            sector_prices[sym] = {
                "price": pos.get("current_price"),
                "day_pnl_pct": pos.get("day_pnl_pct", 0),
            }

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "spy_price": market.get("spy_price"),
        "spy_change_pct": market.get("spy_change_pct"),
        "vix": market.get("vix"),
        "vix_change_pct": market.get("vix_change_pct"),
        "market_regime": market.get("regime") or market.get("rotation_theme", "unknown"),
        "market_trend": market.get("trend", "unknown"),
        "sector_etfs": sector_prices,
        "portfolio_equity": portfolio.get("equity"),
        "portfolio_day_pnl": portfolio.get("day_pnl"),
        "portfolio_day_pnl_pct": portfolio.get("day_pnl_pct"),
        "portfolio_cash": portfolio.get("cash"),
        "position_count": len(positions),
    }


def _load_state() -> dict:
    """Load state.json."""
    state_file = paths.live_state
    if state_file.exists():
        try:
            with open(state_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading state.json: {e}")
    return {}
