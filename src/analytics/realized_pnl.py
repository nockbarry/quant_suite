"""Realized P&L from broker fill history — the missing last link of the
feedback loop.

Before this module, only 1 of 492 executed decisions had a realized_pnl:
exit prices were never written back, so the entire learning stack (belief
updater, learnings, calibration) ran on unrealized marks and narrative.

Pipeline:
  1. fetch_filled_orders()  — page the FULL Alpaca order history (read-only)
  2. fifo_realize()         — FIFO-match sells against buy lots (pure function)
  3. rebuild_lots()         — wipe + reinsert realized_lots (derived table,
                              idempotent by construction)
  4. writeback_decisions()  — stamp realized_pnl/exit onto matching executed
                              SELL/TRIM/CLOSE decisions (same symbol, nearest
                              execution_time within a day)
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Fill:
    symbol: str
    side: str          # "buy" | "sell"
    qty: float
    price: float
    filled_at: datetime
    order_id: str


@dataclass
class RealizedLot:
    symbol: str
    qty: float
    entry_price: float
    exit_price: float
    entry_time: Optional[datetime]
    exit_time: datetime
    buy_order_id: Optional[str]
    sell_order_id: str

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.qty

    @property
    def pnl_pct(self) -> float:
        basis = self.entry_price * self.qty
        return (self.pnl / basis * 100.0) if basis else 0.0

    @property
    def hold_days(self) -> float:
        if not self.entry_time:
            return 0.0
        return (self.exit_time - self.entry_time).total_seconds() / 86400.0


def fetch_filled_orders(trading_client) -> list[Fill]:
    """Page the complete closed-order history into Fill records (oldest first)."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    fills: dict[str, Fill] = {}
    until = None
    for _ in range(40):  # 40 pages x 500 = 20k orders, far beyond history size
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED, limit=500, direction="desc",
            **({"until": until} if until else {}),
        )
        batch = trading_client.get_orders(req)
        if not batch:
            break
        for o in batch:
            if str(o.status.value) != "filled" or not o.filled_at:
                continue
            oid = str(o.id)
            if oid in fills:
                continue
            try:
                fills[oid] = Fill(
                    symbol=o.symbol,
                    side=str(o.side.value),
                    qty=float(o.filled_qty),
                    price=float(o.filled_avg_price),
                    filled_at=o.filled_at.replace(tzinfo=None),
                    order_id=oid,
                )
            except (TypeError, ValueError):
                continue
        oldest = min(o.submitted_at for o in batch if o.submitted_at)
        if until is not None and oldest >= until:
            break  # no progress — stop
        until = oldest
        if len(batch) < 500:
            break
    out = sorted(fills.values(), key=lambda f: f.filled_at)
    logger.info(f"Fetched {len(out)} fills "
                f"({out[0].filled_at.date()} .. {out[-1].filled_at.date()})" if out else "No fills")
    return out


def fifo_realize(fills: list[Fill]) -> list[RealizedLot]:
    """FIFO-match sells against open buy lots, per symbol. Pure function.

    Sells with no matching inventory (positions predating history, or data
    gaps) are matched with entry_price=exit_price (zero P&L) and flagged via
    buy_order_id=None — visible, not silently dropped.
    """
    open_lots: dict[str, deque] = {}
    realized: list[RealizedLot] = []
    for f in sorted(fills, key=lambda x: x.filled_at):
        lots = open_lots.setdefault(f.symbol, deque())
        if f.side == "buy":
            lots.append([f.qty, f.price, f.filled_at, f.order_id])
            continue
        remaining = f.qty
        while remaining > 1e-9:
            if not lots:
                logger.warning(f"{f.symbol}: sell {remaining:g} with no inventory — zero-P&L lot")
                realized.append(RealizedLot(
                    symbol=f.symbol, qty=remaining,
                    entry_price=f.price, exit_price=f.price,
                    entry_time=None, exit_time=f.filled_at,
                    buy_order_id=None, sell_order_id=f.order_id,
                ))
                remaining = 0.0
                break
            lot = lots[0]
            take = min(remaining, lot[0])
            realized.append(RealizedLot(
                symbol=f.symbol, qty=take,
                entry_price=lot[1], exit_price=f.price,
                entry_time=lot[2], exit_time=f.filled_at,
                buy_order_id=lot[3], sell_order_id=f.order_id,
            ))
            lot[0] -= take
            remaining -= take
            if lot[0] <= 1e-9:
                lots.popleft()
    return realized


def rebuild_lots(lots: list[RealizedLot], instance_id: str = "default") -> int:
    """Wipe and reinsert the realized_lots table for this instance (idempotent)."""
    from src.db.database import get_db
    from src.db.models import RealizedLotRecord

    with get_db() as session:
        session.query(RealizedLotRecord).filter(
            RealizedLotRecord.instance_id == instance_id
        ).delete()
        for l in lots:
            session.add(RealizedLotRecord(
                symbol=l.symbol, qty=l.qty,
                entry_price=l.entry_price, exit_price=l.exit_price,
                entry_time=l.entry_time, exit_time=l.exit_time,
                hold_days=l.hold_days, pnl=l.pnl, pnl_pct=l.pnl_pct,
                buy_order_id=l.buy_order_id, sell_order_id=l.sell_order_id,
                instance_id=instance_id,
            ))
    return len(lots)


def writeback_decisions(lots: list[RealizedLot]) -> int:
    """Stamp realized P&L onto matching executed sell-side decisions.

    Aggregates lots per sell order, then matches each sell to the nearest
    executed SELL/TRIM/CLOSE decision for that symbol within 1 day. Overwrites
    (derived data) so re-runs stay consistent.
    """
    from src.db.database import get_db
    from src.db.models import DecisionRecord

    by_sell: dict[str, list[RealizedLot]] = {}
    for l in lots:
        by_sell.setdefault(l.sell_order_id, []).append(l)

    updated = 0
    with get_db() as session:
        for sell_id, group in by_sell.items():
            exit_time = group[0].exit_time
            symbol = group[0].symbol
            pnl = sum(l.pnl for l in group)
            basis = sum(l.entry_price * l.qty for l in group)
            pnl_pct = pnl / basis * 100.0 if basis else 0.0
            entry_times = [l.entry_time for l in group if l.entry_time]
            hold_days = ((exit_time - min(entry_times)).days if entry_times else None)

            candidates = (
                session.query(DecisionRecord)
                .filter(
                    DecisionRecord.symbol == symbol,
                    DecisionRecord.action.in_(["SELL", "TRIM", "CLOSE"]),
                    DecisionRecord.status == "executed",
                    DecisionRecord.execution_time >= exit_time - timedelta(days=1),
                    DecisionRecord.execution_time <= exit_time + timedelta(days=1),
                )
                .all()
            )
            if not candidates:
                continue
            best = min(candidates, key=lambda d: abs((d.execution_time - exit_time).total_seconds()))
            best.realized_pnl = pnl
            best.realized_pnl_pct = pnl_pct
            best.exit_price = group[0].exit_price
            best.exit_time = exit_time
            if hold_days is not None:
                best.actual_hold_days = hold_days
            updated += 1
    return updated


def summarize(lots: list[RealizedLot]) -> dict:
    """Headline stats: total realized P&L, win rate, avg, by hold-duration."""
    matched = [l for l in lots if l.buy_order_id]  # exclude zero-P&L inventory gaps
    if not matched:
        return {"lots": 0}
    wins = [l for l in matched if l.pnl > 0]
    total = sum(l.pnl for l in matched)
    short = [l for l in matched if l.hold_days <= 10]
    long_ = [l for l in matched if l.hold_days > 10]
    return {
        "lots": len(matched),
        "unmatched_inventory_lots": len(lots) - len(matched),
        "total_realized_pnl": round(total, 2),
        "win_rate": round(len(wins) / len(matched), 3),
        "avg_pnl_pct": round(sum(l.pnl_pct for l in matched) / len(matched), 2),
        "avg_hold_days": round(sum(l.hold_days for l in matched) / len(matched), 1),
        "short_hold_pnl": round(sum(l.pnl for l in short), 2),
        "long_hold_pnl": round(sum(l.pnl for l in long_), 2),
    }
