#!/usr/bin/env python3
"""Cron job: build the shadow TargetPortfolio from live beliefs (Phase 2).

Schedule: 6:15 AM ET Mon-Fri (after thesis maintenance, before sessions).

SHADOW MODE — read-only. Builds the desired portfolio from active theses via
the conviction ladder, persists a snapshot to target_portfolios, and logs the
gap vs current positions. It does NOT trade; the Reconciler (Phase 4) consumes
these snapshots once validated.

This is where we observe whether conviction-driven sizing + the invested band
deploy the chronic ~40% idle cash sensibly before anything acts on it.

Usage:
    PYTHONPATH=. python3 scripts/cron_build_target.py
"""

import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("build-target")


def _load_state() -> dict:
    p = Path(os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results")))
    with open(p / "live" / "state.json") as f:
        return json.load(f)


def main() -> int:
    from src.core.events import emit
    from src.db.database import init_db
    from src.knowledge.thesis import ThesisTracker
    from src.portfolio.builder import TargetPortfolioBuilder
    from src.portfolio.store import load_cash_policy, save_target

    init_db()
    state = _load_state()
    equity = float(state.get("portfolio", {}).get("equity", 0.0) or 0.0)
    if equity <= 0:
        logger.warning("No equity in state.json — skipping target build")
        return 0

    # Current positions -> weights, for the gap report
    current: dict[str, float] = {}
    for pos in state.get("positions", []):
        mv = pos.get("market_value")
        try:
            mv = float(mv)
        except (TypeError, ValueError):
            continue
        if mv:
            current[pos.get("symbol")] = mv / equity

    from src.portfolio.adjustments import compute_rule_adjustments
    from src.portfolio.calibration_bound import get_calibration_bound

    tracker = ThesisTracker()
    cash_policy = load_cash_policy()
    adjustments = compute_rule_adjustments(state.get("positions", []))
    if adjustments:
        logger.info(f"Rule adjustments: {[(a.symbol, a.bounded_by) for a in adjustments]}")
    cal_bound = get_calibration_bound()  # None unless ATHENA_CALIBRATION_BOUND=1
    if cal_bound:
        logger.info("Opinion-derived calibration bound ENABLED")
    tp = TargetPortfolioBuilder(tracker, cash_policy=cash_policy).build(
        equity=equity, extra_adjustments=adjustments, calibration_bound=cal_bound,
    )
    tid = save_target(tp, source="builder")
    if cash_policy.reserves:
        active = [r.name for r in cash_policy.reserves if r.active(tp.generated_at.date())]
        logger.info(f"Active reserves: {active or 'none'} "
                    f"(holding {cash_policy.named_reserve_pct(tp.generated_at.date()):.1%})")

    cur_invested = sum(current.values())
    logger.info(
        f"Target {tid}: invested {tp.invested_pct():.1%} (cash {tp.cash_pct():.1%}) "
        f"vs current invested {cur_invested:.1%} (cash {1 - cur_invested:.1%})"
    )

    # Per-symbol gap (target - current), largest moves first
    symbols = set(tp.weights) | set(current)
    gaps = []
    for s in symbols:
        tgt = tp.weights[s].weight if s in tp.weights else 0.0
        cur = current.get(s, 0.0)
        gaps.append((s, cur, tgt, tgt - cur))
    gaps.sort(key=lambda x: -abs(x[3]))
    logger.info("Largest target gaps (symbol: current -> target  Δ$):")
    for s, cur, tgt, d in gaps[:12]:
        logger.info(f"  {s:6} {cur:6.1%} -> {tgt:6.1%}  {d * equity:+9,.0f}")

    emit(
        "target_portfolio_built",
        source="cron_build_target",
        severity="info",
        title=f"Shadow target: {tp.invested_pct():.0%} invested vs {cur_invested:.0%} current",
        detail={
            "target_id": tid,
            "target_invested_pct": round(tp.invested_pct(), 4),
            "current_invested_pct": round(cur_invested, 4),
            "cash_to_deploy_usd": round((tp.invested_pct() - cur_invested) * equity, 0),
            "n_positions": len(tp.weights),
            "mode": "shadow",
        },
    )
    logger.info("Shadow target build complete (no orders submitted).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
