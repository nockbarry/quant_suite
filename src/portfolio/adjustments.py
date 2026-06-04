"""Rule-engine actions, expressed as TargetPortfolio overrides (Phase 5).

In the imperative system these were scattered AUTO rules (rules_engine.py) and
auto_corrections.py queue items, each with its own cooldown — the source of the
re-fire bugs (cooldown only counted applied=true, so failed actions re-fired
forever). Here they become declarative `extra_adjustments` the builder folds in:
re-applying the same adjustment is a no-op once the target is reached, so no
cooldown bookkeeping is needed and the bug class disappears.

What's folded vs. already subsumed by the builder:
  * stop_loss            -> here (weight 0): the one rule not otherwise covered.
  * thesis_invalidation  -> subsumed: conviction < 35 yields a 0 budget already.
  * concentration_trim   -> subsumed: position (10%) and sector (40%) caps.
  * drawdown_protection  -> subsumed: Reconciler blocks BUY legs when day_pnl<-3%.
"""

from __future__ import annotations

import logging

from src.portfolio.target import TargetWeight

logger = logging.getLogger(__name__)

STOP_LOSS_PCT = -15.0


def compute_rule_adjustments(
    positions: list[dict],
    stop_loss_pct: float = STOP_LOSS_PCT,
) -> list[TargetWeight]:
    """Derive declarative target overrides from current positions.

    Args:
        positions: state.json position dicts (need symbol + unrealized_pnl_pct).
        stop_loss_pct: exit threshold; e.g. -15.0 means -15% unrealized.

    Returns:
        TargetWeight(weight=0) for each position breaching its stop. The builder
        drops these symbols from the target, so the Reconciler sells them.
    """
    adjustments: list[TargetWeight] = []
    for pos in positions:
        sym = pos.get("symbol")
        pnl = pos.get("unrealized_pnl_pct")
        if not sym or pnl is None:
            continue
        try:
            pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        if pnl <= stop_loss_pct:
            adjustments.append(TargetWeight(
                symbol=sym, weight=0.0, source="rule_adjustment",
                bounded_by="stop_loss",
            ))
            logger.info(f"Stop-loss adjustment: {sym} at {pnl:.1f}% -> target 0")
    return adjustments
