"""Autonomous trade executor with safety rails and full provenance logging.

Executes trades within safety constraints, logging every step of the process.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.autonomy.config import ExecutionConfig
from src.autonomy.provenance import log_trade_event, log_event
from src.db.database import get_db
from src.db.models import DecisionRecord, AutonomyCheck
from src.db.sync import sync_decision_to_file


@dataclass
class SafetyCheckResult:
    passed: bool
    reason: str = ""
    details: dict | None = None


class AutonomousExecutor:
    """Execute trades with safety checks and provenance logging."""

    def __init__(self, config: ExecutionConfig | None = None):
        self.config = config or ExecutionConfig()
        self._broker = None

    @property
    def broker(self):
        """Lazy-load broker connection."""
        if self._broker is None:
            from scripts.quick_trade import get_broker
            self._broker = get_broker()
        return self._broker

    def check_safety(self, decision: dict, portfolio: dict) -> SafetyCheckResult:
        """Run all safety checks before execution."""
        symbol = decision.get("symbol", "")
        action = decision.get("action", "")
        size_pct = decision.get("size_pct", 0)
        confidence = decision.get("confidence", 0)

        # Check dry-run mode
        if self.config.dry_run:
            return SafetyCheckResult(False, "Dry-run mode — no execution")

        # Check execution authority
        if self.config.authority == "thesis_only" and not decision.get("thesis_id"):
            return SafetyCheckResult(False, "thesis_only authority: no thesis linked")

        # Check max single trade size
        if size_pct > self.config.max_single_trade_pct:
            return SafetyCheckResult(
                False,
                f"Size {size_pct}% exceeds max {self.config.max_single_trade_pct}%",
            )

        # Check daily trade limit
        trades_today = self._count_today_trades()
        if trades_today >= self.config.max_daily_trades:
            return SafetyCheckResult(
                False,
                f"Daily trade limit reached ({trades_today}/{self.config.max_daily_trades})",
            )

        # Check daily loss limit
        day_pnl_pct = portfolio.get("day_pnl_pct", 0)
        if day_pnl_pct < -self.config.max_daily_loss_pct:
            return SafetyCheckResult(
                False,
                f"Daily loss limit reached ({day_pnl_pct:.1f}% < -{self.config.max_daily_loss_pct}%)",
            )

        # Check options ban
        if len(symbol) > 10 or any(c.isdigit() for c in symbol[3:]):
            return SafetyCheckResult(False, "Options trading is banned (rule 1)")

        # Confidence threshold
        if confidence < self.config.max_single_trade_pct / 100:
            return SafetyCheckResult(False, f"Confidence too low ({confidence:.0%})")

        return SafetyCheckResult(True)

    def _count_today_trades(self) -> int:
        """Count trades executed today."""
        try:
            with get_db() as session:
                today = datetime.utcnow().date()
                count = (
                    session.query(DecisionRecord)
                    .filter(
                        DecisionRecord.status.in_(["executed", "filled"]),
                        DecisionRecord.timestamp >= datetime.combine(today, datetime.min.time()),
                    )
                    .count()
                )
                return count
        except Exception:
            return 0

    async def execute_decision(self, decision: dict, portfolio: dict, parent_event_id: str | None = None) -> dict:
        """Execute a trading decision with full provenance.

        Returns dict with execution result.
        """
        decision_id = decision.get("id", "")
        symbol = decision.get("symbol", "")
        action = decision.get("action", "")

        # Log submission
        evt_id = log_trade_event(
            "trade_submitted",
            decision_id=decision_id,
            symbol=symbol,
            detail={"action": action, "size_pct": decision.get("size_pct", 0)},
            parent_event_id=parent_event_id,
        )

        # Safety checks
        safety = self.check_safety(decision, portfolio)
        if not safety.passed:
            log_trade_event(
                "trade_failed",
                decision_id=decision_id,
                symbol=symbol,
                detail={"action": action, "reason": safety.reason},
                severity="warning",
                parent_event_id=evt_id,
            )
            # Update decision status
            self._update_decision_status(decision_id, "rejected", notes=safety.reason)
            return {"success": False, "reason": safety.reason}

        # Calculate quantity
        total_equity = portfolio.get("total_value", 0)
        if total_equity <= 0:
            return {"success": False, "reason": "No portfolio value"}

        size_pct = decision.get("size_pct", 5.0)
        target_value = total_equity * (size_pct / 100)

        # Get current price (approximate from portfolio or quote)
        current_price = decision.get("limit_price") or self._get_price(symbol)
        if not current_price or current_price <= 0:
            return {"success": False, "reason": f"Cannot determine price for {symbol}"}

        qty = int(target_value / current_price)
        if qty <= 0:
            return {"success": False, "reason": f"Calculated quantity is 0 (${target_value:.0f} / ${current_price:.2f})"}

        # Execute
        try:
            await self.broker.connect()

            if action in ("BUY", "ADD"):
                result = await self.broker.market_buy(symbol, Decimal(qty))
            elif action in ("SELL", "TRIM", "CLOSE"):
                result = await self.broker.market_sell(symbol, Decimal(qty))
            else:
                return {"success": False, "reason": f"Unsupported action: {action}"}

            fill_price = float(getattr(result, "filled_avg_price", current_price))

            # Log fill
            log_trade_event(
                "trade_filled",
                decision_id=decision_id,
                symbol=symbol,
                detail={
                    "action": action,
                    "price": fill_price,
                    "qty": qty,
                    "value": fill_price * qty,
                },
                parent_event_id=evt_id,
            )

            # Update decision record
            self._update_decision_status(
                decision_id,
                "executed",
                execution_price=fill_price,
            )

            return {
                "success": True,
                "fill_price": fill_price,
                "quantity": qty,
                "value": fill_price * qty,
            }

        except Exception as e:
            log_trade_event(
                "trade_failed",
                decision_id=decision_id,
                symbol=symbol,
                detail={"action": action, "reason": str(e)},
                severity="critical",
                parent_event_id=evt_id,
            )
            self._update_decision_status(decision_id, "rejected", notes=str(e))
            return {"success": False, "reason": str(e)}

    def _get_price(self, symbol: str) -> float | None:
        """Get approximate current price."""
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def _update_decision_status(self, decision_id: str, status: str, execution_price: float | None = None, notes: str | None = None):
        """Update decision record in DB and file."""
        try:
            with get_db() as session:
                decision = session.query(DecisionRecord).filter_by(id=decision_id).first()
                if decision:
                    decision.status = status
                    if execution_price:
                        decision.execution_price = execution_price
                        decision.execution_time = datetime.utcnow()
                    if notes:
                        decision.outcome_notes = notes
                    sync_decision_to_file(decision.to_dict())
        except Exception as e:
            print(f"WARN: Failed to update decision status: {e}")
