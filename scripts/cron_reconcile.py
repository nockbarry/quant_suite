#!/usr/bin/env python3
"""Cron job: reconcile the live portfolio toward the latest TargetPortfolio.

Phase 4. Runs in SHADOW by default (--shadow): computes the reconcile plan,
persists planned orders to reconcile_orders, and submits NOTHING. The live
cutover (drop --shadow) is gated behind 1-2 weeks of shadow review per the
migration plan.

    PYTHONPATH=. python3 scripts/cron_reconcile.py --shadow   # plan only (default)
    PYTHONPATH=. python3 scripts/cron_reconcile.py --live      # submit orders

Current positions/equity/prices come from the broker when it connects, else
fall back to state.json (broker-sourced, refreshed every 5 min by the daemon).
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("reconcile")


def _state() -> dict:
    base = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    with open(base / "live" / "state.json") as f:
        return json.load(f)


def _from_state(state: dict):
    """(equity, current_values, prices) from the state.json snapshot."""
    equity = float(state.get("portfolio", {}).get("equity", 0.0) or 0.0)
    current, prices = {}, {}
    for pos in state.get("positions", []):
        sym = pos.get("symbol")
        try:
            mv = float(pos.get("market_value") or 0)
            qty = float(pos.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
        if sym and mv:
            current[sym] = mv
            if qty:
                prices[sym] = mv / qty
    return equity, current, prices


async def _from_broker(target_symbols):
    """(equity, current_values, prices) from the live broker, or None on failure."""
    try:
        from scripts.quick_trade import get_broker
        broker = get_broker(paper=True)
        await broker.connect()
    except Exception as e:
        logger.warning(f"Broker connect failed ({e}); falling back to state.json")
        return None, None, None, None
    try:
        account = await broker.get_account()
        equity = float(account.portfolio_value)
        positions = await broker.get_positions()
        current, prices = {}, {}
        for sym, pos in positions.items():
            current[str(sym)] = float(pos.market_value)
            prices[str(sym)] = float(pos.current_price)
        # quotes for target symbols we don't currently hold
        missing = [s for s in target_symbols if s not in prices]
        if missing:
            quotes = await broker.get_quotes(missing)
            for sym, q in (quotes or {}).items():
                if q and getattr(q, "last", None):
                    prices[str(sym)] = float(q.last)
        return broker, equity, current, prices
    except Exception as e:
        logger.warning(f"Broker fetch failed ({e}); falling back to state.json")
        try:
            await broker.disconnect()
        except Exception:
            pass
        return None, None, None, None


async def main_async(live: bool) -> int:
    from src.core.events import emit
    from src.db.database import init_db
    from src.portfolio.reconciler import Reconciler
    from src.portfolio.store import load_latest_target

    init_db()
    target = load_latest_target()
    if target is None:
        logger.warning("No target portfolio snapshot found — run cron_build_target.py first")
        return 0

    state = _state()
    # drawdown protection safety rail: no new buys if portfolio down 3%+ on day
    day_pnl_pct = float(state.get("portfolio", {}).get("day_pnl_pct", 0.0) or 0.0)
    allow_buys = day_pnl_pct > -3.0

    broker, equity, current, prices = await _from_broker(set(target.weights))
    if equity is None:
        equity, current, prices = _from_state(state)

    if not equity or not prices:
        logger.warning("Insufficient equity/price data — skipping reconcile")
        return 0

    reconciler = Reconciler()
    orders = reconciler.plan(
        target, current_values=current, equity=equity, prices=prices,
        allow_buys=allow_buys,
    )

    mode = "LIVE" if live else "SHADOW"
    if not orders:
        logger.info(f"[{mode}] Portfolio already at target — no orders (no-op).")
    else:
        logger.info(f"[{mode}] Reconcile plan ({len(orders)} orders, buys_allowed={allow_buys}):")
        for o in orders:
            logger.info(f"  {o.side.upper():4} {o.symbol:6} x{o.qty:<5} ~${o.notional:9,.0f}  [{o.reason}]")

    await reconciler.execute(orders, broker, target_id=target.id, dry_run=not live)

    if broker is not None:
        try:
            await broker.disconnect()
        except Exception:
            pass

    emit(
        "portfolio_reconciled",
        source="cron_reconcile",
        severity="info",
        title=f"{mode}: {len(orders)} reconcile orders",
        detail={
            "mode": mode.lower(),
            "target_id": target.id,
            "n_orders": len(orders),
            "buys": sum(1 for o in orders if o.side == "buy"),
            "sells": sum(1 for o in orders if o.side == "sell"),
            "buys_allowed": allow_buys,
        },
    )
    logger.info(f"[{mode}] Reconcile complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile portfolio toward target")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--shadow", action="store_true", help="plan only, submit nothing (default)")
    group.add_argument("--live", action="store_true", help="submit orders to the broker")
    args = parser.parse_args()
    return asyncio.run(main_async(live=args.live))


if __name__ == "__main__":
    sys.exit(main())
