#!/usr/bin/env python3
"""Run ensemble evaluation on pending trade decisions.

Called by cron after /trade-decision sessions, before cron_auto_execute.py.
Reads today's pending decisions from the DB, runs 2 challenger evaluations
each, stores ensemble_data on the DecisionRecord, and marks non-consensus
decisions so cron_auto_execute.py will skip them.

Usage:
    PYTHONPATH=. python3 scripts/run_ensemble.py [--dry-run]
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ensemble] %(message)s")
logger = logging.getLogger(__name__)


def run_ensemble(dry_run: bool = False):
    """Evaluate all recent PENDING decisions through the ensemble."""
    from src.db.database import get_db, init_db
    from src.db.models import DecisionRecord
    from src.decision.ensemble import DecisionEnsemble

    init_db()
    ensemble = DecisionEnsemble()

    # Find PENDING decisions from the last 4 hours (matches cron_auto_execute window)
    cutoff = datetime.now() - timedelta(hours=4)

    with get_db() as session:
        pending = (
            session.query(DecisionRecord)
            .filter(
                DecisionRecord.status == "pending",
                DecisionRecord.action.in_(["BUY", "SELL", "ADD", "TRIM", "CLOSE"]),
                DecisionRecord.timestamp >= cutoff,
            )
            .order_by(DecisionRecord.timestamp)
            .all()
        )

        if not pending:
            logger.info("No pending decisions to evaluate")
            return

        # Filter out decisions that already have ensemble_data
        to_evaluate = []
        for d in pending:
            existing = getattr(d, "ensemble_data", None)
            if existing:
                try:
                    data = json.loads(existing)
                    if data.get("consensus") is not None:
                        logger.info(f"Skipping {d.symbol} {d.action} — already has ensemble data")
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass  # Corrupt data, re-evaluate
            to_evaluate.append(d)

        if not to_evaluate:
            logger.info("All pending decisions already have ensemble data")
            return

        logger.info(f"Evaluating {len(to_evaluate)} decision(s) through ensemble")

        consensus_count = 0
        rejected_count = 0

        for decision in to_evaluate:
            # Build decision dict from DB record
            decision_dict = {
                "id": decision.id,
                "symbol": decision.symbol,
                "action": decision.action,
                "confidence": decision.confidence or 0.5,
                "reasoning": decision.reasoning or "",
                "thesis_name": decision.thesis_id or "No thesis",
                "key_factors": _safe_json(decision.key_factors),
                "risks": _safe_json(decision.risks),
            }

            # Build context from the decision's stored context
            context = _safe_json(decision.context) if decision.context else {}

            if dry_run:
                logger.info(f"[DRY RUN] Would evaluate {decision.symbol} {decision.action}")
                continue

            try:
                result = ensemble.evaluate(decision_dict, context)

                # Store ensemble data on the decision record
                ensemble_data = {
                    "consensus": result.consensus,
                    "consensus_count": result.consensus_count,
                    "final_action": result.final_action,
                    "final_confidence": result.final_confidence,
                    "ensemble_confidence": result.ensemble_confidence,
                    "members": result.members,
                    "timestamp": result.timestamp,
                }
                decision.ensemble_data = json.dumps(ensemble_data)

                # Blend agreement into the linked prediction's calibrated
                # confidence (C4): challengers ran, so the agreement fraction
                # is now known — creation-time confidence had agreement=None.
                try:
                    from src.db.models import PredictionRecord
                    from src.probability.estimator import effective_confidence

                    if len(result.members) > 1:
                        agreement = result.consensus_count / 3.0
                        pred = (
                            session.query(PredictionRecord)
                            .filter(PredictionRecord.decision_id == decision.id)
                            .first()
                        )
                        if pred is not None:
                            stated = pred.stated_confidence or decision.confidence
                            pred.confidence = effective_confidence(stated, agreement)
                except Exception as e:
                    logger.warning(f"Prediction confidence blend failed: {e}")

                # If no consensus, mark status so auto-execute skips it
                if not result.consensus:
                    decision.status = "ensemble_rejected"
                    decision.outcome_notes = (
                        f"Ensemble rejected: {result.consensus_count}/3 consensus "
                        f"(need 2/3). Challengers disagreed with {result.primary_action}."
                    )
                    rejected_count += 1
                else:
                    consensus_count += 1

                session.commit()

            except Exception as e:
                logger.error(f"Ensemble evaluation failed for {decision.symbol}: {e}")
                session.rollback()
                continue

        logger.info(
            f"Ensemble complete: {consensus_count} consensus, {rejected_count} rejected"
            + (" (DRY RUN)" if dry_run else "")
        )

    # Log to ProcessEvent
    try:
        from src.autonomy.provenance import log_event

        log_event(
            "ensemble_complete",
            source="cron:ensemble",
            title=(
                f"Ensemble evaluated {len(to_evaluate)} decisions: "
                f"{consensus_count} consensus, {rejected_count} rejected"
            ),
        )
    except Exception:
        pass


def _safe_json(text):
    """Parse JSON text safely, returning the parsed value or the original."""
    if not text:
        return []
    if isinstance(text, (list, dict)):
        return text
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def main():
    parser = argparse.ArgumentParser(description="Run ensemble evaluation on pending decisions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be evaluated without running challengers",
    )
    args = parser.parse_args()

    run_ensemble(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
