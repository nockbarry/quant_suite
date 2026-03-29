"""Opinion scorer — scores market opinions at each horizon as dates arrive."""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)


class OpinionScorer:
    """Scores market opinions at 5d/10d/30d horizons.

    Scoring metrics per horizon:
    - direction_score: 1.0 if trend_direction matches actual move, 0.0 otherwise
    - range_score: 1.0 if actual price within [bear, bull] targets, 0.0 otherwise
    - proximity_score: continuous 0-1, how close actual is to base target
    - relative_score: 1.0 if relative_direction vs benchmark correct, 0.0 otherwise
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path(
            os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
        )
        self._price_cache: dict[tuple[str, str], float] = {}

    def score_due_opinions(self) -> dict:
        """Find opinions due for scoring at each horizon and score them.

        Returns summary: {"scored_5d": N, "scored_10d": N, "scored_30d": N, "errors": N}
        """
        from src.db.database import get_db
        from src.db.models import MarketOpinionRecord
        from src.db.write_api import athena_db

        now = datetime.utcnow()
        summary = {"scored_5d": 0, "scored_10d": 0, "scored_30d": 0, "errors": 0}

        horizons = [
            (5, "open", "scored_5d"),
            (10, "scored_5d", "scored_10d"),
            (30, "scored_10d", "scored_30d"),
        ]

        for horizon_days, from_status, to_status in horizons:
            try:
                with get_db() as session:
                    # Find opinions due for this horizon
                    cutoff = now - timedelta(days=horizon_days)
                    opinions = session.query(MarketOpinionRecord).filter(
                        MarketOpinionRecord.status == from_status,
                        MarketOpinionRecord.created <= cutoff,
                    ).limit(500).all()

                    if not opinions:
                        continue

                    # Collect unique symbols for batch price lookup
                    symbols = list({o.symbol for o in opinions})
                    logger.info(f"Scoring {len(opinions)} opinions at {horizon_days}d for {len(symbols)} symbols")

                    for opinion in opinions:
                        try:
                            target_date = opinion.created + timedelta(days=horizon_days)
                            actual_price = self._get_price(opinion.symbol, target_date)
                            spy_price_then = self._get_price("SPY", target_date)
                            spy_price_at_opinion = self._get_price("SPY", opinion.created)

                            if actual_price is None or actual_price <= 0:
                                continue

                            scores = self._score_at_horizon(
                                opinion, horizon_days, actual_price,
                                spy_price_at_opinion, spy_price_then,
                            )

                            if athena_db.score_opinion(opinion.id, horizon_days, scores):
                                summary[f"scored_{horizon_days}d"] += 1

                        except Exception as e:
                            logger.warning(f"Error scoring opinion {opinion.id}: {e}")
                            summary["errors"] += 1

            except Exception as e:
                logger.error(f"Error in {horizon_days}d scoring pass: {e}")
                summary["errors"] += 1

        # Write calibration
        self._write_calibration()

        return summary

    def _score_at_horizon(
        self, opinion, horizon: int, actual_price: float,
        spy_at_opinion: float | None, spy_at_horizon: float | None,
    ) -> dict:
        """Score a single opinion at a single horizon."""
        scores: dict = {"actual_price": actual_price}
        entry_price = opinion.price_at_opinion or 0

        if entry_price <= 0:
            return scores

        # 1. Direction score
        actual_direction = "bullish" if actual_price > entry_price else "bearish"
        if actual_price == entry_price:
            actual_direction = "neutral"
        predicted_direction = opinion.trend_direction or "neutral"

        if predicted_direction == "neutral":
            # Neutral prediction: correct if price moved < 1%
            pct_move = abs(actual_price - entry_price) / entry_price
            scores["direction"] = 1.0 if pct_move < 0.01 else 0.0
        else:
            scores["direction"] = 1.0 if predicted_direction == actual_direction else 0.0

        # 2. Range score (was actual within bull/bear bounds?)
        bull = getattr(opinion, f"target_{horizon}d_bull", None) or 0
        bear = getattr(opinion, f"target_{horizon}d_bear", None) or 0
        if bull > 0 and bear > 0:
            scores["range"] = 1.0 if bear <= actual_price <= bull else 0.0
        else:
            scores["range"] = None

        # 3. Proximity score (how close to base target?)
        base = getattr(opinion, f"target_{horizon}d_base", None) or 0
        if base > 0 and bull > 0 and bear > 0:
            range_width = bull - bear
            if range_width > 0:
                error = abs(actual_price - base) / range_width
                scores["proximity"] = max(0.0, 1.0 - error)
            else:
                scores["proximity"] = 1.0 if abs(actual_price - base) < 0.01 else 0.0
        else:
            scores["proximity"] = None

        # 4. Relative performance score
        if spy_at_opinion and spy_at_horizon and spy_at_opinion > 0:
            spy_return = (spy_at_horizon - spy_at_opinion) / spy_at_opinion
            sym_return = (actual_price - entry_price) / entry_price
            actual_alpha = sym_return - spy_return

            scores["actual_relative"] = round(actual_alpha * 100, 2)

            predicted_rel = opinion.relative_direction or "inline"
            if predicted_rel == "outperform":
                scores["score_relative"] = 1.0 if actual_alpha > 0 else 0.0
            elif predicted_rel == "underperform":
                scores["score_relative"] = 1.0 if actual_alpha < 0 else 0.0
            else:  # inline
                scores["score_relative"] = 1.0 if abs(actual_alpha) < 0.02 else 0.0

        return scores

    def _get_price(self, symbol: str, target_date: datetime) -> float | None:
        """Get closing price near target date. Uses cache."""
        date_str = target_date.strftime("%Y-%m-%d")
        key = (symbol, date_str)
        if key in self._price_cache:
            return self._price_cache[key]

        try:
            start = target_date - timedelta(days=5)
            end = target_date + timedelta(days=3)
            data = yf.download(
                symbol,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False,
            )
            if data.empty:
                return None

            # Find closest date to target
            target_ts = target_date.replace(hour=16, minute=0, second=0)
            data.index = data.index.tz_localize(None) if data.index.tz else data.index
            closest_idx = data.index[data.index.get_indexer([target_ts], method="nearest")]
            if len(closest_idx) > 0:
                close_val = data.loc[closest_idx[0], "Close"]
                price = float(close_val.iloc[0]) if hasattr(close_val, 'iloc') else float(close_val)
                if hasattr(price, 'item'):
                    price = price.item()
                self._price_cache[key] = price
                return price
        except Exception as e:
            logger.debug(f"Price lookup failed for {symbol} at {date_str}: {e}")

        return None

    def compute_calibration(self, instance_id: str | None = None) -> dict:
        """Compute opinion calibration bins by trend_confidence."""
        from src.db.database import get_db
        from src.db.models import MarketOpinionRecord

        bins_def = [
            (0.0, 0.4, "0-40%"),
            (0.4, 0.5, "40-50%"),
            (0.5, 0.6, "50-60%"),
            (0.6, 0.7, "60-70%"),
            (0.7, 0.8, "70-80%"),
            (0.8, 0.9, "80-90%"),
            (0.9, 1.01, "90-100%"),
        ]

        try:
            with get_db() as session:
                q = session.query(MarketOpinionRecord).filter(
                    MarketOpinionRecord.score_10d_direction.isnot(None)
                )
                if instance_id:
                    q = q.filter(MarketOpinionRecord.instance_id == instance_id)
                opinions = q.all()

                if not opinions:
                    return {"bins": [], "calibration_error": None, "total_scored": 0}

                bins = []
                for low, high, label in bins_def:
                    bucket = [o for o in opinions if low <= (o.trend_confidence or 0.5) < high]
                    if bucket:
                        dir_acc = sum(o.score_10d_direction for o in bucket) / len(bucket)
                        range_acc = sum(o.score_10d_range or 0 for o in bucket) / len(bucket)
                        avg_conf = sum(o.trend_confidence or 0.5 for o in bucket) / len(bucket)
                        bins.append({
                            "label": label,
                            "predicted_confidence": round(avg_conf, 3),
                            "actual_direction_rate": round(dir_acc, 3),
                            "actual_range_rate": round(range_acc, 3),
                            "count": len(bucket),
                        })

                # Calibration error
                cal_errors = [
                    abs(b["predicted_confidence"] - b["actual_direction_rate"])
                    for b in bins if b["count"] >= 3
                ]
                cal_error = sum(cal_errors) / len(cal_errors) if cal_errors else None

                return {
                    "bins": bins,
                    "calibration_error": round(cal_error, 3) if cal_error else None,
                    "total_scored": len(opinions),
                    "updated_at": datetime.utcnow().isoformat(),
                }

        except Exception as e:
            logger.error(f"Calibration computation failed: {e}")
            return {"error": str(e)}

    def _write_calibration(self) -> None:
        """Write opinion calibration to JSON file."""
        cal = self.compute_calibration()
        out_path = self.results_dir / "intelligence" / "opinion_calibration.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_path.write_text(json.dumps(cal, indent=2))
            logger.info(f"Wrote opinion calibration: {cal.get('total_scored', 0)} scored")
        except Exception as e:
            logger.error(f"Failed to write calibration: {e}")
