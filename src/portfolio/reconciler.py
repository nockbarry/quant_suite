"""Reconciler — trade the live portfolio toward a TargetPortfolio.

Replaces opportunistic per-decision execution (cron_auto_execute.py). Core
properties:
  * Declarative: computes diff(current, target); at-target => empty plan (no-op).
  * Idempotent: each order has a deterministic client_order_id; re-running the
    same plan the same day yields the same ids, which Alpaca rejects as dupes.
  * Safety-railed: per-trade size cap, optional buy-block on drawdown, min-trade
    threshold, max orders/day. Reuses RiskLimitsConfig.

plan() is pure and synchronous (unit-testable). execute() is async and does I/O.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.portfolio.target import TargetPortfolio
from src.risk.limits import RiskLimitsConfig

logger = logging.getLogger(__name__)


@dataclass
class ReconcileOrder:
    """One leg of a reconciliation plan."""

    symbol: str
    side: str                 # "buy" | "sell"
    qty: int
    client_order_id: str
    target_weight: float
    current_value: float
    target_value: float
    est_price: float
    reason: str = ""
    status: str = "planned"
    metadata: dict = field(default_factory=dict)

    @property
    def notional(self) -> float:
        return self.qty * self.est_price

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "qty": self.qty,
            "client_order_id": self.client_order_id,
            "target_weight": round(self.target_weight, 4),
            "notional": round(self.notional, 2),
            "reason": self.reason,
            "status": self.status,
        }


class Reconciler:
    """Computes and (optionally) executes reconciliation toward a target."""

    def __init__(
        self,
        config: Optional[RiskLimitsConfig] = None,
        min_trade_usd: float = 200.0,
        min_trade_weight: float = 0.005,
        max_orders_per_run: int = 10,
    ):
        self.config = config or RiskLimitsConfig()
        self.min_trade_usd = min_trade_usd
        self.min_trade_weight = min_trade_weight
        self.max_orders_per_run = max_orders_per_run

    @staticmethod
    def _client_order_id(today: str, symbol: str, side: str, qty: int) -> str:
        """Deterministic, idempotent, <=48 chars, alphanumeric+dash."""
        # e.g. recon-20260603-NVDA-b12  (date 8 + symbol<=5 + side 1 + qty)
        coid = f"recon-{today}-{symbol}-{side[0]}{qty}"
        return coid[:48]

    def plan(
        self,
        target: TargetPortfolio,
        current_values: dict[str, float],
        equity: float,
        prices: dict[str, float],
        *,
        today: Optional[str] = None,
        allow_buys: bool = True,
        block_buy_reason: str = "drawdown",
    ) -> list[ReconcileOrder]:
        """Diff current vs target into idempotent orders.

        Args:
            target: desired portfolio.
            current_values: symbol -> current market value (USD).
            equity: total account equity (USD).
            prices: symbol -> last price (USD). Symbols without a price are skipped.
            allow_buys: if False, only SELL legs are emitted (drawdown protection).
        """
        if equity <= 0:
            return []
        today = today or datetime.now().strftime("%Y%m%d")
        max_trade_usd = self.config.max_trade_pct * equity

        symbols = set(target.weights) | set(current_values)
        candidates: list[ReconcileOrder] = []
        for sym in symbols:
            tw = target.weights.get(sym)
            target_weight = tw.weight if tw else 0.0
            target_value = target_weight * equity
            current_value = current_values.get(sym, 0.0)
            delta = target_value - current_value

            # min-trade threshold (skip tiny rebalances -> at-target is a no-op)
            if abs(delta) < self.min_trade_usd or abs(delta) / equity < self.min_trade_weight:
                continue

            price = prices.get(sym)
            if not price or price <= 0:
                logger.warning(f"No price for {sym}; skipping reconcile leg")
                continue

            side = "buy" if delta > 0 else "sell"
            if side == "buy" and not allow_buys:
                continue  # drawdown protection: trims allowed, adds blocked

            # per-trade size cap (safety rail)
            capped = min(abs(delta), max_trade_usd)
            reason = "reconcile" if capped == abs(delta) else f"partial:max_trade_{self.config.max_trade_pct:.0%}"
            qty = int(capped / price)
            if qty < 1:
                continue

            coid = self._client_order_id(today, sym, side, qty)
            candidates.append(ReconcileOrder(
                symbol=sym, side=side, qty=qty, client_order_id=coid,
                target_weight=target_weight, current_value=current_value,
                target_value=target_value, est_price=price, reason=reason,
            ))

        # Prioritize the largest moves; sells first (free up buying power, and
        # are always allowed). Cap orders per run.
        candidates.sort(key=lambda o: (o.side != "sell", -abs(o.target_value - o.current_value)))
        if len(candidates) > self.max_orders_per_run:
            dropped = candidates[self.max_orders_per_run:]
            logger.info(f"Capping at {self.max_orders_per_run} orders/run; deferring {len(dropped)}: "
                        f"{[o.symbol for o in dropped]}")
            candidates = candidates[:self.max_orders_per_run]
        return candidates

    async def execute(
        self,
        orders: list[ReconcileOrder],
        broker,
        target_id: Optional[str] = None,
        dry_run: bool = True,
    ) -> list[ReconcileOrder]:
        """Persist the plan; submit orders only when dry_run is False.

        In shadow mode (dry_run=True) every order is recorded status='planned'
        and nothing is sent. Live mode submits with the deterministic
        client_order_id and records submitted/skipped/rejected.
        """
        for o in orders:
            if dry_run:
                o.status = "planned"
                self._persist(o, target_id)
                continue
            if self._already_submitted(o.client_order_id):
                o.status = "skipped"
                o.reason = "duplicate_client_order_id"
                continue
            try:
                kwargs = {"metadata": {"client_order_id": o.client_order_id}}
                if o.side == "buy":
                    res = await broker.market_buy(o.symbol, Decimal(o.qty), **kwargs)
                else:
                    res = await broker.market_sell(o.symbol, Decimal(o.qty), **kwargs)
                o.status = "submitted"
                # Alpaca returns a UUID for order_id; coerce to str so it binds
                # to the String column (sqlite rejects raw UUID objects).
                oid = getattr(res, "order_id", None)
                o.metadata["alpaca_order_id"] = str(oid) if oid is not None else None
            except Exception as e:
                msg = str(e).lower()
                o.status = "skipped" if "client_order_id" in msg or "duplicate" in msg else "rejected"
                o.reason = f"{o.reason}; {str(e)[:80]}"
                logger.warning(f"Reconcile {o.side} {o.symbol} x{o.qty} -> {o.status}: {e}")
            self._persist(o, target_id)
        return orders

    @staticmethod
    def _persist(o: ReconcileOrder, target_id: Optional[str]) -> None:
        from src.db.database import get_db
        from src.db.models import ReconcileOrderRecord
        try:
            with get_db() as session:
                existing = (
                    session.query(ReconcileOrderRecord)
                    .filter(ReconcileOrderRecord.client_order_id == o.client_order_id)
                    .one_or_none()
                )
                if existing is None:
                    existing = ReconcileOrderRecord(client_order_id=o.client_order_id)
                    session.add(existing)
                existing.target_id = target_id
                existing.symbol = o.symbol
                existing.side = o.side
                existing.qty = o.qty
                existing.target_weight = o.target_weight
                existing.status = o.status
                existing.alpaca_order_id = o.metadata.get("alpaca_order_id")
                existing.reason = o.reason
                if o.status == "submitted":
                    existing.submitted_at = datetime.now()
        except Exception as e:
            logger.warning(f"Failed to persist reconcile order {o.client_order_id}: {e}")

    @staticmethod
    def _already_submitted(client_order_id: str) -> bool:
        from src.db.database import get_db
        from src.db.models import ReconcileOrderRecord
        try:
            with get_db() as session:
                row = (
                    session.query(ReconcileOrderRecord)
                    .filter(ReconcileOrderRecord.client_order_id == client_order_id)
                    .one_or_none()
                )
                return row is not None and row.status in ("submitted", "filled")
        except Exception:
            return False
