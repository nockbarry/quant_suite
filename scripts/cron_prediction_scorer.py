#!/usr/bin/env python3
"""Automated prediction scorer — run 5:15 PM weekdays.

Resolves open predictions whose resolve_by date has passed:
1. Fetches current/historical prices
2. Scores each prediction by type
3. Calculates Brier score
4. Expires stale predictions (>5 days past deadline)

Cron:
    15 17 * * 1-5 cd /home/nock/projects/quant_suite && PYTHONPATH=. python3 scripts/cron_prediction_scorer.py
"""

import logging
import sys
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def get_current_price(symbol: str) -> float | None:
    """Get current price via yfinance (cached)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol}: {e}")
        return None


def score_prediction(pred: dict, current_price: float | None) -> dict | None:
    """Score a single prediction. Returns resolution dict or None if can't score."""
    pred_type = pred.get("prediction_type", "")
    direction = pred.get("direction", "bullish")
    target_value = pred.get("target_value")
    confidence = pred.get("confidence", 0.5)

    if pred_type == "direction":
        if current_price is None:
            return None
        # Need a reference price — use target_value as baseline if available,
        # otherwise we can't score without entry price
        # For backfilled predictions, target_value often holds the entry price
        baseline = target_value
        if baseline is None or baseline <= 0:
            return {"status": "expired", "notes": "No baseline price to compare"}

        actual_direction = "bullish" if current_price > baseline else "bearish"
        hit = actual_direction == direction
        outcome = 1.0 if hit else 0.0
        brier = (confidence - outcome) ** 2

        return {
            "status": "hit" if hit else "miss",
            "actual_value": current_price,
            "notes": f"Predicted {direction}, actual move {((current_price / baseline) - 1) * 100:+.1f}%",
            "brier_score": round(brier, 4),
            "accuracy_score": outcome,
        }

    elif pred_type == "price_target":
        if current_price is None or target_value is None:
            return None

        if direction == "bullish":
            hit = current_price >= target_value
        else:
            hit = current_price <= target_value

        outcome = 1.0 if hit else 0.0
        brier = (confidence - outcome) ** 2

        return {
            "status": "hit" if hit else "miss",
            "actual_value": current_price,
            "notes": f"Target ${target_value:.2f}, actual ${current_price:.2f}",
            "brier_score": round(brier, 4),
            "accuracy_score": outcome,
        }

    elif pred_type == "timeframe_move":
        if current_price is None or target_value is None:
            return None

        # target_value is expected % move, actual_value stored as entry price
        baseline = pred.get("actual_value") or target_value
        if baseline and baseline > 0 and target_value != 0:
            actual_pct = ((current_price / baseline) - 1) * 100
            # For timeframe_move, target_value is the % target
            hit = (direction == "bullish" and actual_pct >= target_value) or \
                  (direction == "bearish" and actual_pct <= -abs(target_value))
            outcome = 1.0 if hit else 0.0
            brier = (confidence - outcome) ** 2

            return {
                "status": "hit" if hit else "miss",
                "actual_value": current_price,
                "notes": f"Target {target_value:+.1f}%, actual {actual_pct:+.1f}%",
                "brier_score": round(brier, 4),
                "accuracy_score": outcome,
            }
        return {"status": "expired", "notes": "Insufficient data for timeframe_move scoring"}

    elif pred_type == "event_outcome":
        # Manual scoring required
        return None

    elif pred_type == "thesis_validation":
        # Manual scoring required
        return None

    elif pred_type == "relative_perf":
        # Would need second symbol data — skip for auto-scoring
        return None

    return None


def run_scorer():
    """Main scorer loop."""
    from src.db.database import get_db, init_db
    from src.db.models import PredictionRecord
    from src.db.write_api import athena_db

    init_db()

    now = datetime.utcnow()
    expire_cutoff = now - timedelta(days=5)
    scored = 0
    expired = 0
    skipped = 0

    with get_db() as session:
        # Get predictions due for resolution
        due = session.query(PredictionRecord).filter(
            PredictionRecord.status == "open",
            PredictionRecord.resolve_by <= now,
        ).all()

        logger.info(f"Found {len(due)} predictions due for scoring")

        # Group by symbol to minimize price fetches
        by_symbol: dict[str, list] = {}
        for pred in due:
            by_symbol.setdefault(pred.symbol, []).append(pred.to_dict())

    # Score outside the session to avoid long locks
    for symbol, preds in by_symbol.items():
        price = get_current_price(symbol)
        for pred in preds:
            # Expire very old predictions
            resolve_by = pred.get("resolve_by")
            if resolve_by:
                try:
                    rb = datetime.fromisoformat(resolve_by)
                    if rb < expire_cutoff:
                        athena_db.resolve_prediction(
                            pred["id"],
                            status="expired",
                            notes=f"Auto-expired: >5 days past deadline ({resolve_by[:10]})",
                            brier_score=None,
                            accuracy_score=0.0,
                        )
                        expired += 1
                        continue
                except (ValueError, TypeError):
                    pass

            result = score_prediction(pred, price)
            if result:
                athena_db.resolve_prediction(
                    pred["id"],
                    status=result["status"],
                    actual_value=result.get("actual_value"),
                    notes=result.get("notes", ""),
                    brier_score=result.get("brier_score"),
                    accuracy_score=result.get("accuracy_score"),
                    timing_error_days=result.get("timing_error_days"),
                )
                scored += 1
            else:
                skipped += 1

    logger.info(f"Prediction scoring complete: {scored} scored, {expired} expired, {skipped} skipped")
    return scored, expired, skipped


if __name__ == "__main__":
    scored, expired, skipped = run_scorer()
    print(f"Scored: {scored}, Expired: {expired}, Skipped: {skipped}")
