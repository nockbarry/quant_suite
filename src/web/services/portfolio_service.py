"""Portfolio service — fetch positions and orders from paper and live Alpaca accounts."""

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _make_sync(coro_fn, *args, **kwargs):
    """Run async function synchronously (for use in sync route context)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context — create a new thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro_fn(*args, **kwargs))
            return future.result(timeout=15)
    else:
        return asyncio.run(coro_fn(*args, **kwargs))


async def _fetch_account_data(paper: bool) -> dict:
    """Fetch account info, positions, and recent orders from Alpaca."""
    from src.execution.broker.alpaca import AlpacaBroker
    import yaml
    from pathlib import Path

    config_path = Path(__file__).parent.parent.parent.parent / "config" / "credentials.yaml"
    if not config_path.exists():
        return {"error": "credentials.yaml not found", "account": None, "positions": [], "orders": []}

    with open(config_path) as f:
        config = yaml.safe_load(f)

    alpaca = config.get("alpaca", {})
    api_key = alpaca.get("api_key")
    secret_key = alpaca.get("secret_key")

    if not paper:
        # Check if live trading is enabled
        if not config.get("live_trading_enabled", False):
            alpaca_live = config.get("alpaca_live", {})
            if not alpaca_live.get("api_key"):
                return {
                    "error": None,
                    "disabled": True,
                    "account": None,
                    "positions": [],
                    "orders": [],
                    "label": "Live",
                    "is_paper": False,
                }
        alpaca_live = config.get("alpaca_live", {})
        if alpaca_live.get("api_key"):
            api_key = alpaca_live["api_key"]
            secret_key = alpaca_live["secret_key"]

    broker = AlpacaBroker(api_key=api_key, secret_key=secret_key, paper=paper)

    try:
        await broker.connect()
    except Exception as e:
        logger.warning(f"Failed to connect to {'paper' if paper else 'live'} broker: {e}")
        return {
            "error": str(e),
            "account": None,
            "positions": [],
            "orders": [],
            "label": "Paper" if paper else "Live",
            "is_paper": paper,
        }

    try:
        account = await broker.get_account()
        positions_map = await broker.get_positions()
        open_orders = await broker.get_open_orders()

        positions = []
        for sym, pos in positions_map.items():
            positions.append({
                "symbol": str(sym),
                "quantity": float(pos.quantity),
                "entry_price": float(pos.entry_price),
                "current_price": float(pos.current_price),
                "market_value": float(pos.market_value),
                "unrealized_pnl": float(pos.unrealized_pnl),
                "unrealized_pnl_pct": float(pos.unrealized_pnl_pct),
            })

        positions.sort(key=lambda p: p["unrealized_pnl_pct"], reverse=True)

        orders = []
        for order in open_orders:
            orders.append({
                "order_id": order.order_id,
                "symbol": str(order.symbol),
                "side": order.side.value if hasattr(order.side, 'value') else str(order.side),
                "quantity": float(order.quantity),
                "order_type": order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
                "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                "limit_price": float(order.limit_price) if order.limit_price else None,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            })

        total_value = sum(p["market_value"] for p in positions)
        total_pnl = sum(p["unrealized_pnl"] for p in positions)

        return {
            "error": None,
            "disabled": False,
            "label": "Paper" if paper else "Live",
            "is_paper": paper,
            "account": {
                "account_id": account.account_id,
                "equity": float(account.portfolio_value),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "day_trade_count": account.day_trade_count,
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
            },
            "positions": positions,
            "position_count": len(positions),
            "total_value": total_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": (total_pnl / total_value * 100) if total_value else 0,
            "orders": orders,
        }
    except Exception as e:
        logger.error(f"Error fetching {'paper' if paper else 'live'} data: {e}")
        return {
            "error": str(e),
            "account": None,
            "positions": [],
            "orders": [],
            "label": "Paper" if paper else "Live",
            "is_paper": paper,
        }
    finally:
        try:
            await broker.disconnect()
        except Exception:
            pass


async def fetch_both_accounts() -> dict:
    """Fetch paper and live account data in parallel."""
    paper_task = asyncio.create_task(_fetch_account_data(paper=True))
    live_task = asyncio.create_task(_fetch_account_data(paper=False))

    paper_data, live_data = await asyncio.gather(paper_task, live_task, return_exceptions=True)

    if isinstance(paper_data, Exception):
        paper_data = {"error": str(paper_data), "label": "Paper", "is_paper": True, "positions": [], "orders": [], "account": None}
    if isinstance(live_data, Exception):
        live_data = {"error": str(live_data), "label": "Live", "is_paper": False, "positions": [], "orders": [], "account": None}

    return {
        "paper": paper_data,
        "live": live_data,
        "fetched_at": datetime.utcnow().isoformat(),
    }


async def fetch_single_account(paper: bool = True) -> dict:
    """Fetch a single account's data."""
    return await _fetch_account_data(paper=paper)
