"""Persistence for TargetPortfolio snapshots (target_portfolios table) and
the standing CashPolicy (invested band + named reserves) on disk."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths
from src.db.database import get_db
from src.db.models import TargetPortfolioRecord
from src.portfolio.target import CashPolicy, TargetPortfolio, TargetWeight


def _cash_policy_path() -> Path:
    return paths.live / "cash_policy.json"


def load_cash_policy() -> CashPolicy:
    """Load the standing cash policy (band + reserves) from disk, or default."""
    p = _cash_policy_path()
    if not p.exists():
        return CashPolicy()
    try:
        return CashPolicy.from_dict(json.loads(p.read_text()))
    except Exception:
        return CashPolicy()


def save_cash_policy(cp: CashPolicy) -> None:
    """Persist the cash policy (band + reserves) to disk."""
    p = _cash_policy_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cp.to_dict(), indent=2))


def save_target(tp: TargetPortfolio, source: str = "builder") -> str:
    """Persist a TargetPortfolio snapshot; returns its id."""
    tid = tp.id or f"target-{uuid.uuid4().hex[:12]}"
    tp.id = tid
    today = tp.generated_at.date()
    with get_db() as session:
        rec = TargetPortfolioRecord(
            id=tid,
            generated_at=tp.generated_at,
            equity_at_build=tp.equity_at_build,
            weights_json=json.dumps([w.to_dict() for w in tp.weights.values()]),
            cash_policy_json=json.dumps(tp.cash_policy.to_dict(today=today)),
            invested_pct=tp.invested_pct(),
            reserve_pct=tp.cash_policy.named_reserve_pct(today),
            source=source,
            reconciled=False,
        )
        session.add(rec)
    return tid


def load_latest_target() -> Optional[TargetPortfolio]:
    """Load the most recent target snapshot (any reconciled state)."""
    with get_db() as session:
        rec = (
            session.query(TargetPortfolioRecord)
            .order_by(TargetPortfolioRecord.generated_at.desc())
            .first()
        )
        if rec is None:
            return None
        weights = {
            w["symbol"]: TargetWeight.from_dict(w)
            for w in json.loads(rec.weights_json or "[]")
        }
        cash_policy = CashPolicy.from_dict(json.loads(rec.cash_policy_json or "{}"))
        return TargetPortfolio(
            weights=weights,
            cash_policy=cash_policy,
            generated_at=rec.generated_at or datetime.now(),
            equity_at_build=rec.equity_at_build or 0.0,
            id=rec.id,
        )
