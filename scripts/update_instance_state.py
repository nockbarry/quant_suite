#!/usr/bin/env python3
"""Synchronous state.json updater for secondary Athena instances.

The LiveDaemon is async and requires an event loop, which doesn't work well
in cron's sync context. This script does a synchronous equivalent:
1. Reads QUANT_RESULTS_DIR and ATHENA_INSTANCE from env
2. Connects to the instance's Alpaca account via InstanceConfig
3. Fetches positions and account data
4. Writes state.json in the format matching the default daemon

Usage (cron):
    QUANT_RESULTS_DIR=~/quant_results_beta ATHENA_INSTANCE=beta \
        PYTHONPATH=. python3 scripts/update_instance_state.py

    QUANT_RESULTS_DIR=~/quant_results_gamma ATHENA_INSTANCE=gamma \
        PYTHONPATH=. python3 scripts/update_instance_state.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from src.core.paths import paths
from src.core.instance import instance_config
from src.risk.stress_tester import SYMBOL_SECTOR_MAP


def get_alpaca_client():
    """Create Alpaca TradingClient using instance-specific credentials."""
    try:
        import yaml
        from alpaca.trading.client import TradingClient
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        sys.exit(1)

    creds_path = instance_config.credentials_path()
    logger.info(f"Loading credentials from: {creds_path}")

    with open(creds_path) as f:
        creds = yaml.safe_load(f)

    return TradingClient(
        creds["alpaca"]["api_key"],
        creds["alpaca"]["secret_key"],
        paper=True,
    )


def fetch_account(client) -> dict:
    """Fetch account info and build portfolio snapshot."""
    account = client.get_account()
    equity = float(account.equity)
    last_equity = float(account.last_equity)
    day_pl = equity - last_equity

    return {
        "timestamp": datetime.now().isoformat(),
        "equity": equity,
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "day_pnl": round(day_pl, 2),
        "day_pnl_pct": round((day_pl / last_equity) * 100, 2) if last_equity > 0 else 0,
        "total_positions": 0,  # set below
        "market_exposure_pct": 0.0,  # set below
        "day_trades_remaining": 3,
        "pdt_restricted": getattr(account, "pattern_day_trader", False),
    }


def fetch_positions(client) -> list[dict]:
    """Fetch all positions and build position snapshots."""
    positions = []
    alpaca_positions = client.get_all_positions()

    for p in alpaca_positions:
        positions.append({
            "symbol": p.symbol,
            "quantity": int(float(p.qty)),
            "avg_cost": float(p.avg_entry_price),
            "current_price": float(p.current_price),
            "market_value": float(p.market_value),
            "unrealized_pnl": float(p.unrealized_pl),
            "unrealized_pnl_pct": round(float(p.unrealized_plpc) * 100, 2),
            "day_pnl": float(p.unrealized_intraday_pl),
            "day_pnl_pct": round(float(p.unrealized_intraday_plpc) * 100, 2),
            "weight_pct": 0.0,
            "sector": SYMBOL_SECTOR_MAP.get(p.symbol, "other"),
            "days_held": 0,
            "thesis_id": None,
            "distance_to_stop_pct": None,
            "distance_to_target_pct": None,
        })

    return positions


def link_theses(positions: list[dict]) -> None:
    """Link positions to thesis objects if theses exist."""
    try:
        from src.knowledge.thesis import ThesisTracker
        tracker = ThesisTracker()
        symbol_map = {}
        for thesis in tracker.get_active_theses():
            for sym in (thesis.positions or []):
                symbol_map[sym] = thesis.id

        for pos in positions:
            pos["thesis_id"] = symbol_map.get(pos["symbol"])
    except Exception as e:
        logger.debug(f"Thesis linking skipped: {e}")


def compute_weights(positions: list[dict], equity: float) -> None:
    """Compute position weights as percent of equity."""
    if equity <= 0:
        return
    for pos in positions:
        pos["weight_pct"] = round(
            abs(float(pos["market_value"])) / equity * 100, 2
        )


def build_state(portfolio: dict, positions: list[dict]) -> dict:
    """Build the full state.json structure."""
    now = datetime.now()

    # Determine if market is open (simple weekday + hours check)
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    time_minutes = hour * 60 + minute
    market_open = (
        weekday < 5
        and (9 * 60 + 30) <= time_minutes <= (16 * 60)
    )

    # Update portfolio counts
    portfolio["total_positions"] = len(positions)
    if portfolio["equity"] > 0:
        total_mv = sum(abs(float(p["market_value"])) for p in positions)
        portfolio["market_exposure_pct"] = round(
            (total_mv / portfolio["equity"]) * 100, 2
        )

    return {
        "timestamp": now.isoformat(),
        "market_open": market_open,
        "last_updated_by": "update_instance_state",
        "market": {
            "timestamp": now.isoformat(),
            "spy_price": 0.0,
            "spy_change_pct": 0.0,
            "qqq_price": 0.0,
            "qqq_change_pct": 0.0,
            "vix": 0.0,
            "vix_change_pct": 0.0,
            "advance_decline_ratio": 1.0,
            "new_highs": 0,
            "new_lows": 0,
            "leading_sectors": [],
            "lagging_sectors": [],
            "rotation_theme": "unknown",
            "regime": "unknown",
            "regime_confidence": 0.0,
        },
        "sentiment": {
            "timestamp": now.isoformat(),
            "fear_greed_value": 50.0,
            "fear_greed_label": "neutral",
            "put_call_ratio": 1.0,
            "put_call_signal": "neutral",
            "vix_term_structure": "unknown",
            "overall_sentiment": "neutral",
            "contrarian_signal": None,
        },
        "portfolio": portfolio,
        "positions": positions,
        "risk": {
            "timestamp": now.isoformat(),
            "portfolio_var_1d": 0.0,
            "portfolio_var_pct": 0.0,
            "max_position_weight": max(
                (p["weight_pct"] for p in positions), default=0.0
            ),
            "max_sector_weight": 0.0,
            "correlation_risk": "unknown",
            "concentration_warning": None,
            "limit_breaches": [],
        },
        "watchlist_signals": {},
        "theses": [],
        "pending_decisions": [],
        "recent_learnings": [],
        "alerts": [],
        "upcoming_events": [],
        "research": {"total_documents": 0, "recent": []},
        "summary": "",
        "summary_text": "",
    }


def main():
    instance = instance_config.instance_name()
    results = instance_config.results_dir()
    state_path = paths.live_state

    logger.info(f"Instance: {instance}")
    logger.info(f"Results dir: {results}")
    logger.info(f"State output: {state_path}")

    # Ensure output directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    # Fetch data from Alpaca
    try:
        client = get_alpaca_client()
    except Exception as e:
        logger.error(f"Failed to create Alpaca client: {e}")
        sys.exit(1)

    try:
        portfolio = fetch_account(client)
        logger.info(f"Account: equity=${portfolio['equity']:,.0f}, cash=${portfolio['cash']:,.0f}")
    except Exception as e:
        logger.error(f"Failed to fetch account: {e}")
        sys.exit(1)

    try:
        positions = fetch_positions(client)
        logger.info(f"Positions: {len(positions)}")
    except Exception as e:
        logger.error(f"Failed to fetch positions: {e}")
        positions = []

    # Compute weights and link theses
    compute_weights(positions, portfolio["equity"])
    link_theses(positions)

    # Build and write state
    state = build_state(portfolio, positions)

    # Generate summary text
    top_positions = sorted(positions, key=lambda p: abs(p["market_value"]), reverse=True)[:5]
    summary_parts = [
        f"Instance {instance}: ${portfolio['equity']:,.0f} equity, "
        f"{len(positions)} positions, "
        f"day P&L: ${portfolio['day_pnl']:+,.0f} ({portfolio['day_pnl_pct']:+.2f}%)",
    ]
    if top_positions:
        top_str = ", ".join(
            f"{p['symbol']} ({p['weight_pct']:.1f}%)" for p in top_positions
        )
        summary_parts.append(f"Top 5: {top_str}")
    state["summary_text"] = " | ".join(summary_parts)

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    logger.info(f"State written to {state_path}")
    logger.info(f"Summary: {state['summary_text']}")


if __name__ == "__main__":
    main()
