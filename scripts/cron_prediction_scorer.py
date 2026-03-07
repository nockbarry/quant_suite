#!/usr/bin/env python3
"""Automated prediction scorer — run 5:15 PM weekdays.

Resolves open predictions using three strategies:
1. PAST DUE: resolve_by date has passed — score against current price
2. EARLY RESOLVE: clear directional outcome before deadline (>10% move)
3. EXPIRE: >5 days past deadline and still unscorable

Key fixes over original:
- Recovers missing baseline prices from decision records or yfinance history
- Processes ALL open predictions, not just past-due ones
- Early-resolves predictions with decisive outcomes (>10% move in predicted direction
  or >5% move against) even before resolve_by date
- Backfills target_value on predictions that are missing it for future runs

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

# Cache for yfinance ticker objects to avoid repeated API calls
_yf_cache: dict[str, object] = {}


def get_current_price(symbol: str) -> float | None:
    """Get current/latest close price via yfinance."""
    try:
        import yfinance as yf
        if symbol not in _yf_cache:
            _yf_cache[symbol] = yf.Ticker(symbol)
        ticker = _yf_cache[symbol]
        hist = ticker.history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"Price fetch failed for {symbol}: {e}")
        return None


def get_historical_price(symbol: str, target_date: datetime) -> float | None:
    """Get close price on or near a specific date via yfinance.

    Used to recover baseline/entry prices for predictions that are missing target_value.
    Fetches a window around the target date to handle weekends/holidays.
    """
    try:
        import yfinance as yf
        if symbol not in _yf_cache:
            _yf_cache[symbol] = yf.Ticker(symbol)
        ticker = _yf_cache[symbol]

        # Fetch a 10-day window around the target date
        start = (target_date - timedelta(days=5)).strftime("%Y-%m-%d")
        end = (target_date + timedelta(days=3)).strftime("%Y-%m-%d")
        hist = ticker.history(start=start, end=end)
        if hist.empty:
            return None

        # Find closest date on or before target
        target_ts = target_date.replace(tzinfo=hist.index[0].tzinfo) if hist.index[0].tzinfo else target_date
        on_or_before = hist[hist.index <= target_ts]
        if not on_or_before.empty:
            return float(on_or_before["Close"].iloc[-1])
        # If target is before all data, use the first available
        return float(hist["Close"].iloc[0])
    except Exception as e:
        logger.debug(f"Historical price fetch failed for {symbol} @ {target_date.date()}: {e}")
        return None


def recover_baseline_price(pred: dict, decision_map: dict) -> float | None:
    """Try to recover a baseline/entry price for a prediction missing target_value.

    Strategy order:
    1. Decision record: execution_price or limit_price
    2. yfinance historical price on prediction creation date
    """
    # Strategy 1: Check linked decision record
    decision_id = pred.get("decision_id")
    if decision_id and decision_id in decision_map:
        d = decision_map[decision_id]
        entry = d.get("execution_price") or d.get("limit_price")
        if entry and entry > 0:
            logger.debug(f"Recovered baseline ${entry:.2f} for {pred['symbol']} from decision {decision_id[:20]}")
            return entry

    # Strategy 2: Historical price from yfinance at prediction creation date
    created_str = pred.get("created")
    if created_str:
        try:
            created_dt = datetime.fromisoformat(created_str)
            hist_price = get_historical_price(pred["symbol"], created_dt)
            if hist_price and hist_price > 0:
                logger.debug(f"Recovered baseline ${hist_price:.2f} for {pred['symbol']} from yfinance @ {created_dt.date()}")
                return hist_price
        except (ValueError, TypeError):
            pass

    return None


def score_prediction(pred: dict, current_price: float | None, baseline: float | None = None) -> dict | None:
    """Score a single prediction. Returns resolution dict or None if can't score.

    Args:
        pred: Prediction dict from PredictionRecord.to_dict()
        current_price: Latest market price for the symbol
        baseline: Override baseline price (recovered from decision or yfinance)
    """
    pred_type = pred.get("prediction_type", "")
    direction = pred.get("direction", "bullish")
    target_value = pred.get("target_value")
    confidence = pred.get("confidence", 0.5)

    if pred_type == "direction":
        if current_price is None:
            return None

        # Use target_value as baseline, fall back to recovered baseline
        entry_price = target_value if (target_value and target_value > 0) else baseline
        if entry_price is None or entry_price <= 0:
            return None  # Return None instead of expiring — we may recover later

        pct_move = ((current_price / entry_price) - 1) * 100
        actual_direction = "bullish" if current_price > entry_price else "bearish"
        hit = actual_direction == direction
        outcome = 1.0 if hit else 0.0
        brier = (confidence - outcome) ** 2

        return {
            "status": "hit" if hit else "miss",
            "actual_value": current_price,
            "notes": f"Predicted {direction}, actual move {pct_move:+.1f}% (baseline ${entry_price:.2f})",
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

        # Proximity scoring: continuous 0-1+ metric (how close to target)
        # Parse entry price from target_description if available
        desc = pred.get("target_description", "")
        entry_price = baseline
        if not entry_price and "bear=$" in desc:
            # Extract bear price as rough entry proxy
            import re
            bear_match = re.search(r'bear=\$([\d.]+)', desc)
            if bear_match:
                entry_price = float(bear_match.group(1))

        proximity_score = None
        if entry_price and entry_price > 0 and target_value != entry_price:
            if direction == "bullish":
                proximity_score = (current_price - entry_price) / (target_value - entry_price)
            else:
                proximity_score = (entry_price - current_price) / (entry_price - target_value)
            proximity_score = round(max(0.0, proximity_score), 4)

        prox_note = f", proximity={proximity_score:.1%}" if proximity_score is not None else ""

        return {
            "status": "hit" if hit else "miss",
            "actual_value": current_price,
            "notes": f"Target ${target_value:.2f}, actual ${current_price:.2f}{prox_note}",
            "brier_score": round(brier, 4),
            "accuracy_score": proximity_score if proximity_score is not None else outcome,
        }

    elif pred_type == "timeframe_move":
        if current_price is None or target_value is None:
            return None

        # target_value is expected % move; need an entry price as baseline
        # Check actual_value field first (sometimes stores entry price), then recovered baseline
        entry_price = pred.get("actual_value") or baseline
        if not entry_price or entry_price <= 0:
            return None

        actual_pct = ((current_price / entry_price) - 1) * 100
        hit = (direction == "bullish" and actual_pct >= target_value) or \
              (direction == "bearish" and actual_pct <= -abs(target_value))
        outcome = 1.0 if hit else 0.0
        brier = (confidence - outcome) ** 2

        return {
            "status": "hit" if hit else "miss",
            "actual_value": current_price,
            "notes": f"Target {target_value:+.1f}%, actual {actual_pct:+.1f}% (baseline ${entry_price:.2f})",
            "brier_score": round(brier, 4),
            "accuracy_score": outcome,
        }

    elif pred_type in ("event_outcome", "thesis_validation", "relative_perf"):
        # These require manual scoring
        return None

    return None


def check_early_resolve(pred: dict, current_price: float | None, baseline: float | None = None) -> dict | None:
    """Check if a prediction can be resolved early due to a decisive move.

    Early resolution thresholds:
    - Direction predictions: >10% move in predicted direction = early hit,
      >5% move against predicted direction = early miss
    - This avoids waiting for the resolve_by date when the outcome is already clear

    Returns resolution dict or None if move isn't decisive enough yet.
    """
    pred_type = pred.get("prediction_type", "")
    direction = pred.get("direction", "bullish")
    target_value = pred.get("target_value")
    confidence = pred.get("confidence", 0.5)

    if pred_type != "direction":
        return None  # Only early-resolve directional predictions

    if current_price is None:
        return None

    entry_price = target_value if (target_value and target_value > 0) else baseline
    if entry_price is None or entry_price <= 0:
        return None

    pct_move = ((current_price / entry_price) - 1) * 100

    # Early hit: large move in predicted direction
    EARLY_HIT_PCT = 10.0
    # Early miss: meaningful move against predicted direction
    EARLY_MISS_PCT = 5.0

    if direction == "bullish":
        if pct_move >= EARLY_HIT_PCT:
            outcome = 1.0
            brier = (confidence - outcome) ** 2
            return {
                "status": "hit",
                "actual_value": current_price,
                "notes": f"Early resolve: predicted bullish, moved {pct_move:+.1f}% (>{EARLY_HIT_PCT}% threshold, baseline ${entry_price:.2f})",
                "brier_score": round(brier, 4),
                "accuracy_score": outcome,
            }
        elif pct_move <= -EARLY_MISS_PCT:
            outcome = 0.0
            brier = (confidence - outcome) ** 2
            return {
                "status": "miss",
                "actual_value": current_price,
                "notes": f"Early resolve: predicted bullish, moved {pct_move:+.1f}% (<-{EARLY_MISS_PCT}% threshold, baseline ${entry_price:.2f})",
                "brier_score": round(brier, 4),
                "accuracy_score": outcome,
            }
    elif direction == "bearish":
        if pct_move <= -EARLY_HIT_PCT:
            outcome = 1.0
            brier = (confidence - outcome) ** 2
            return {
                "status": "hit",
                "actual_value": current_price,
                "notes": f"Early resolve: predicted bearish, moved {pct_move:+.1f}% (<-{EARLY_HIT_PCT}% threshold, baseline ${entry_price:.2f})",
                "brier_score": round(brier, 4),
                "accuracy_score": outcome,
            }
        elif pct_move >= EARLY_MISS_PCT:
            outcome = 0.0
            brier = (confidence - outcome) ** 2
            return {
                "status": "miss",
                "actual_value": current_price,
                "notes": f"Early resolve: predicted bearish, moved {pct_move:+.1f}% (>{EARLY_MISS_PCT}% threshold, baseline ${entry_price:.2f})",
                "brier_score": round(brier, 4),
                "accuracy_score": outcome,
            }

    return None


def backfill_baseline(pred_id: str, baseline: float):
    """Persist recovered baseline price for future scoring runs.

    For direction predictions: stores in target_value (the entry/baseline price).
    For timeframe_move predictions: stores in actual_value (the entry price field,
    since target_value holds the % move target).

    This ensures the next run won't need to re-fetch historical data.
    """
    from src.db.database import get_db
    from src.db.models import PredictionRecord

    try:
        with get_db() as session:
            pred = session.query(PredictionRecord).filter(
                PredictionRecord.id == pred_id
            ).first()
            if not pred:
                return

            if pred.prediction_type == "timeframe_move":
                if pred.actual_value is None:
                    pred.actual_value = baseline
                    logger.info(f"Backfilled actual_value=${baseline:.2f} (entry price) on timeframe_move prediction {pred_id[:30]}")
            else:
                if pred.target_value is None:
                    pred.target_value = baseline
                    logger.info(f"Backfilled target_value=${baseline:.2f} on prediction {pred_id[:30]}")
    except Exception as e:
        logger.debug(f"Failed to backfill baseline for {pred_id}: {e}")


def run_scorer():
    """Main scorer loop.

    Three passes:
    1. Past-due predictions (resolve_by <= now) — score or expire
    2. Not-yet-due predictions — check for early resolution on decisive moves
    3. Backfill recovered baseline prices on predictions missing target_value
    """
    from src.db.database import get_db, init_db
    from src.db.models import PredictionRecord, DecisionRecord
    from src.db.write_api import athena_db

    init_db()

    now = datetime.utcnow()
    expire_cutoff = now - timedelta(days=5)
    scored = 0
    expired = 0
    skipped = 0
    early_resolved = 0
    baselines_recovered = 0

    # Load all open predictions and their linked decisions in one go
    with get_db() as session:
        all_open = session.query(PredictionRecord).filter(
            PredictionRecord.status == "open",
        ).all()
        all_open_dicts = [p.to_dict() for p in all_open]

        # Build decision map for baseline recovery
        decision_ids = {p.decision_id for p in all_open if p.decision_id}
        decision_map = {}
        if decision_ids:
            decisions = session.query(DecisionRecord).filter(
                DecisionRecord.id.in_(decision_ids)
            ).all()
            decision_map = {d.id: d.to_dict() for d in decisions}

    # Separate into past-due and not-yet-due
    past_due = []
    not_yet_due = []
    for pred in all_open_dicts:
        resolve_by_str = pred.get("resolve_by")
        if resolve_by_str:
            try:
                rb = datetime.fromisoformat(resolve_by_str)
                if rb <= now:
                    past_due.append(pred)
                else:
                    not_yet_due.append(pred)
            except (ValueError, TypeError):
                past_due.append(pred)  # If unparseable, treat as due
        else:
            past_due.append(pred)  # No resolve_by = due immediately

    logger.info(f"Open predictions: {len(all_open_dicts)} total, {len(past_due)} past due, {len(not_yet_due)} not yet due")

    # Collect all unique symbols across both sets
    all_symbols = {p["symbol"] for p in all_open_dicts}

    # Skip symbols that look like options contracts (contain digits after letters)
    valid_symbols = set()
    for sym in all_symbols:
        if len(sym) > 6 and any(c.isdigit() for c in sym[3:]):
            logger.debug(f"Skipping options-like symbol: {sym}")
        else:
            valid_symbols.add(sym)

    # Fetch current prices for all needed symbols
    logger.info(f"Fetching prices for {len(valid_symbols)} symbols...")
    price_map: dict[str, float | None] = {}
    for symbol in valid_symbols:
        price_map[symbol] = get_current_price(symbol)

    # Recover baselines for predictions missing target_value (direction type)
    # or missing actual_value entry price (timeframe_move type)
    baseline_map: dict[str, float | None] = {}  # pred_id -> baseline
    for pred in all_open_dicts:
        needs_baseline = False
        if pred.get("prediction_type") == "timeframe_move":
            # timeframe_move uses actual_value as entry price, target_value is the % target
            if not pred.get("actual_value") or pred["actual_value"] <= 0:
                needs_baseline = True
        else:
            # direction and other types use target_value as baseline
            if not pred.get("target_value") or pred["target_value"] <= 0:
                needs_baseline = True

        if not needs_baseline:
            continue

        recovered = recover_baseline_price(pred, decision_map)
        if recovered:
            baseline_map[pred["id"]] = recovered
            baselines_recovered += 1

    logger.info(f"Recovered {baselines_recovered} baseline prices from decisions/yfinance")

    # === PASS 1: Score past-due predictions ===
    for pred in past_due:
        symbol = pred["symbol"]
        price = price_map.get(symbol)
        baseline = baseline_map.get(pred["id"])

        # Expire very old predictions (>5 days past deadline)
        resolve_by_str = pred.get("resolve_by")
        if resolve_by_str:
            try:
                rb = datetime.fromisoformat(resolve_by_str)
                if rb < expire_cutoff:
                    # Even for very old, try to score if we can
                    result = score_prediction(pred, price, baseline)
                    if result and result["status"] in ("hit", "miss"):
                        athena_db.resolve_prediction(
                            pred["id"],
                            status=result["status"],
                            actual_value=result.get("actual_value"),
                            notes=result.get("notes", "") + " (scored late, >5d past deadline)",
                            brier_score=result.get("brier_score"),
                            accuracy_score=result.get("accuracy_score"),
                        )
                        scored += 1
                        continue
                    else:
                        # Truly unscorable and very old — expire
                        athena_db.resolve_prediction(
                            pred["id"],
                            status="expired",
                            actual_value=price,
                            notes=f"Auto-expired: >5 days past deadline ({resolve_by_str[:10]}), no baseline recoverable",
                            brier_score=None,
                            accuracy_score=0.0,
                        )
                        expired += 1
                        continue
            except (ValueError, TypeError):
                pass

        # Normal scoring for past-due predictions
        result = score_prediction(pred, price, baseline)
        if result and result["status"] in ("hit", "miss"):
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
        elif result and result.get("status") == "expired":
            athena_db.resolve_prediction(
                pred["id"],
                status="expired",
                actual_value=price,
                notes=result.get("notes", ""),
                brier_score=None,
                accuracy_score=0.0,
            )
            expired += 1
        else:
            skipped += 1

    # === PASS 2: Early-resolve not-yet-due predictions with decisive moves ===
    for pred in not_yet_due:
        symbol = pred["symbol"]
        price = price_map.get(symbol)
        baseline = baseline_map.get(pred["id"])

        result = check_early_resolve(pred, price, baseline)
        if result:
            athena_db.resolve_prediction(
                pred["id"],
                status=result["status"],
                actual_value=result.get("actual_value"),
                notes=result.get("notes", ""),
                brier_score=result.get("brier_score"),
                accuracy_score=result.get("accuracy_score"),
            )
            early_resolved += 1

    # === PASS 3: Backfill baseline prices on predictions that were missing them ===
    for pred_id, baseline in baseline_map.items():
        # Only backfill if the prediction is still open (wasn't just resolved)
        backfill_baseline(pred_id, baseline)

    logger.info(
        f"Prediction scoring complete: "
        f"{scored} scored, {early_resolved} early-resolved, "
        f"{expired} expired, {skipped} skipped, "
        f"{baselines_recovered} baselines recovered"
    )
    return scored, expired, skipped, early_resolved


if __name__ == "__main__":
    scored, expired, skipped, early_resolved = run_scorer()
    print(f"Scored: {scored}, Early-resolved: {early_resolved}, Expired: {expired}, Skipped: {skipped}")
