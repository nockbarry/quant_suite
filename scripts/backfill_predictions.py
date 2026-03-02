#!/usr/bin/env python3
"""One-time backfill: create PredictionRecords from existing DecisionRecords.

Extracts implicit predictions from:
- Direction (every BUY implies bullish)
- take_profit_pct / expected_hold_days (implies timeframe_move)
- realized_pnl_pct (auto-resolves closed decisions)

Also normalizes setup_type strings to canonical taxonomy.

Idempotent: safe to run multiple times (checks for existing predictions).

Usage:
    PYTHONPATH=. python3 scripts/backfill_predictions.py
    PYTHONPATH=. python3 scripts/backfill_predictions.py --dry-run
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def backfill_predictions(dry_run: bool = False):
    """Create predictions from existing decisions."""
    from src.db.database import get_db, init_db
    from src.db.models import DecisionRecord, PredictionRecord
    from src.db.write_api import athena_db
    from src.intelligence.setup_types import normalize_setup_type

    init_db()

    # Get all existing prediction IDs to avoid duplicates
    existing_pred_decision_ids = set()
    with get_db() as session:
        existing = session.query(PredictionRecord.decision_id).filter(
            PredictionRecord.decision_id.isnot(None)
        ).all()
        existing_pred_decision_ids = {r[0] for r in existing}

    # Get all decisions
    with get_db() as session:
        decisions = session.query(DecisionRecord).order_by(
            DecisionRecord.timestamp.asc()
        ).all()
        decisions_data = [d.to_dict() for d in decisions]

    created = 0
    resolved = 0
    normalized = 0

    for d in decisions_data:
        decision_id = d["id"]

        # Skip if already has predictions
        if decision_id in existing_pred_decision_ids:
            continue

        symbol = d.get("symbol", "")
        action = d.get("action", "")
        confidence = d.get("confidence", 0.5)
        timestamp = d.get("timestamp", "")

        if not symbol or action not in ("BUY", "SELL", "ADD", "TRIM", "CLOSE"):
            continue

        # Determine direction from action
        if action in ("BUY", "ADD"):
            direction = "bullish"
        elif action in ("SELL", "CLOSE", "TRIM"):
            direction = "bearish"
        else:
            direction = "neutral"

        # Determine reasoning category from setup_type
        raw_setup = d.get("setup_type", "thesis_driven")
        setup_type = normalize_setup_type(raw_setup)
        reasoning_category = setup_type  # They map 1:1 for most cases

        # Compute timeframe
        expected_hold = d.get("expected_hold_days", 10) or 10
        base_time = datetime.fromisoformat(timestamp) if timestamp else datetime.utcnow()

        # Create direction prediction
        entry_price = d.get("execution_price") or d.get("limit_price")

        pred_data = {
            "decision_id": decision_id,
            "thesis_id": d.get("thesis_id"),
            "symbol": symbol,
            "prediction_type": "direction",
            "direction": direction,
            "target_value": entry_price,  # Store entry price as baseline
            "target_description": f"{'Bullish' if direction == 'bullish' else 'Bearish'} on {symbol} ({action})",
            "confidence": confidence,
            "timeframe_days": expected_hold,
            "resolve_by": (base_time + timedelta(days=expected_hold)).isoformat(),
            "reasoning_category": reasoning_category,
            "setup_type": setup_type,
            "key_reasoning": d.get("reasoning", "")[:500],
            "created": timestamp,
        }

        if dry_run:
            logger.info(f"[DRY RUN] Would create prediction for {symbol} {action} ({decision_id[:20]}...)")
            created += 1
        else:
            pred_id = athena_db.save_prediction(pred_data)
            created += 1

            # Auto-resolve if decision has outcome
            realized_pnl_pct = d.get("realized_pnl_pct")
            if realized_pnl_pct is not None:
                if direction == "bullish":
                    hit = realized_pnl_pct > 0
                else:
                    hit = realized_pnl_pct < 0

                outcome = 1.0 if hit else 0.0
                brier = (confidence - outcome) ** 2

                athena_db.resolve_prediction(
                    pred_id,
                    status="hit" if hit else "miss",
                    actual_value=d.get("exit_price"),
                    notes=f"Backfilled from decision: P&L {realized_pnl_pct:+.1f}%",
                    brier_score=round(brier, 4),
                    accuracy_score=outcome,
                )
                resolved += 1

        # Normalize setup_type on decision if it changed
        if raw_setup != setup_type and not dry_run:
            try:
                from src.web.services.decision_service import update_decision
                update_decision(decision_id, {"setup_type": setup_type})
                normalized += 1
            except Exception as e:
                logger.debug(f"Setup type normalization failed for {decision_id}: {e}")

    # Run initial calibration
    if not dry_run and created > 0:
        try:
            from src.intelligence.belief_updater import BeliefUpdater
            updater = BeliefUpdater()
            cal = updater._update_calibration()
            logger.info(f"Initial calibration computed: {cal.get('total_resolved', 0)} predictions")
        except Exception as e:
            logger.warning(f"Initial calibration failed: {e}")

    return created, resolved, normalized


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill predictions from decisions")
    parser.add_argument("--dry-run", action="store_true", help="Don't write, just show what would happen")
    args = parser.parse_args()

    created, resolved, normalized = backfill_predictions(dry_run=args.dry_run)
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{prefix}Backfill complete:")
    print(f"  Predictions created: {created}")
    print(f"  Auto-resolved: {resolved}")
    print(f"  Setup types normalized: {normalized}")
