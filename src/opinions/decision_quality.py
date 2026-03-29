"""Decision quality tracker — scores each trade decision's outcome over time."""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)


class DecisionQualityTracker:
    """Tracks price trajectory after each trade decision.

    For every BUY/SELL/ADD/TRIM, records the actual price at
    1d/5d/10d/30d after execution to build quality curves.

    Quality is action-adjusted:
    - BUY/ADD: quality = 1.0 if return > 0, 0.0 otherwise
    - SELL/CLOSE/TRIM: quality = 1.0 if return < 0 (avoided loss), 0.0 otherwise
    """

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path(
            os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results"))
        )
        self.instance_id = os.environ.get("ATHENA_INSTANCE", "auto")
        if self.instance_id == "default":
            self.instance_id = "auto"
        self._price_cache: dict[tuple[str, str], float] = {}

    def backfill_untracked_decisions(self) -> int:
        """Create DecisionQualityRecord for executed decisions without one."""
        from src.db.database import get_db
        from src.db.models import DecisionQualityRecord, DecisionRecord
        from src.db.write_api import athena_db

        count = 0
        try:
            with get_db() as session:
                # Find executed decisions without quality records
                existing_ids = {
                    r.decision_id for r in
                    session.query(DecisionQualityRecord.decision_id).all()
                }

                decisions = session.query(DecisionRecord).filter(
                    DecisionRecord.status.in_(["executed", "completed"]),
                    DecisionRecord.action.in_(["BUY", "SELL", "ADD", "TRIM", "CLOSE"]),
                ).all()

                # Filter out options symbols (contain digits in the middle, e.g. HAL260206C00032000)
                import re
                _options_re = re.compile(r"^[A-Z]+\d{6}[CP]\d+$")
                decisions = [d for d in decisions if not _options_re.match(d.symbol)]

                for d in decisions:
                    if d.id in existing_ids:
                        continue

                    exec_price = d.execution_price or d.limit_price
                    exec_date = d.execution_time or d.timestamp

                    if not exec_price or not exec_date:
                        continue

                    dq_id = athena_db.save_decision_quality({
                        "decision_id": d.id,
                        "instance_id": self.instance_id,
                        "symbol": d.symbol,
                        "action": d.action,
                        "execution_price": exec_price,
                        "execution_date": exec_date.isoformat() if isinstance(exec_date, datetime) else exec_date,
                    })
                    if dq_id:
                        count += 1

            logger.info(f"Backfilled {count} decision quality records")
        except Exception as e:
            logger.error(f"Decision quality backfill failed: {e}")

        return count

    def score_due_decisions(self) -> dict:
        """Check prices at 1d/5d/10d/30d horizons for tracked decisions.

        Returns: {"scored_1d": N, "scored_5d": N, "scored_10d": N, "scored_30d": N}
        """
        from src.db.database import get_db
        from src.db.models import DecisionQualityRecord
        from src.db.write_api import athena_db

        now = datetime.utcnow()
        summary = {"scored_1d": 0, "scored_5d": 0, "scored_10d": 0, "scored_30d": 0, "errors": 0}

        try:
            with get_db() as session:
                records = session.query(DecisionQualityRecord).filter(
                    DecisionQualityRecord.execution_price.isnot(None),
                    DecisionQualityRecord.execution_date.isnot(None),
                ).all()

                for rec in records:
                    exec_price = rec.execution_price
                    exec_date = rec.execution_date
                    if not exec_price or not exec_date:
                        continue

                    updates = {}
                    for horizon in (1, 5, 10, 30):
                        price_col = f"price_{horizon}d"
                        if getattr(rec, price_col) is not None:
                            continue  # Already scored

                        target_date = exec_date + timedelta(days=horizon)
                        if target_date > now:
                            continue  # Not due yet

                        actual = self._get_price(rec.symbol, target_date)
                        spy_at_exec = self._get_price("SPY", exec_date)
                        spy_at_target = self._get_price("SPY", target_date)

                        if actual is None or actual <= 0:
                            continue

                        ret = (actual - exec_price) / exec_price
                        spy_ret = (
                            (spy_at_target - spy_at_exec) / spy_at_exec
                            if spy_at_exec and spy_at_target and spy_at_exec > 0
                            else 0
                        )

                        # Quality is action-adjusted
                        if rec.action in ("BUY", "ADD"):
                            quality = 1.0 if ret > 0 else 0.0
                        elif rec.action in ("SELL", "CLOSE", "TRIM"):
                            quality = 1.0 if ret < 0 else 0.0  # Avoided further loss
                        else:
                            quality = 0.5

                        updates[f"price_{horizon}d"] = actual
                        updates[f"return_{horizon}d"] = round(ret * 100, 2)
                        updates[f"quality_{horizon}d"] = quality
                        updates[f"spy_return_{horizon}d"] = round(spy_ret * 100, 2)
                        summary[f"scored_{horizon}d"] += 1

                    if updates:
                        athena_db.update_decision_quality(rec.decision_id, updates)

        except Exception as e:
            logger.error(f"Decision quality scoring failed: {e}")
            summary["errors"] += 1

        # Write summary file
        self._write_quality_summary()

        return summary

    def get_quality_curve(
        self, instance_id: str | None = None, horizon: int = 10
    ) -> list[dict]:
        """Cumulative quality curve: rolling average quality score over time."""
        from src.db.database import get_db
        from src.db.models import DecisionQualityRecord

        try:
            with get_db() as session:
                q = session.query(DecisionQualityRecord).filter(
                    getattr(DecisionQualityRecord, f"quality_{horizon}d").isnot(None)
                ).order_by(DecisionQualityRecord.execution_date)

                if instance_id:
                    q = q.filter(DecisionQualityRecord.instance_id == instance_id)

                records = q.all()
                if not records:
                    return []

                curve = []
                running_sum = 0.0
                for i, rec in enumerate(records):
                    quality = getattr(rec, f"quality_{horizon}d")
                    running_sum += quality
                    avg = running_sum / (i + 1)
                    curve.append({
                        "date": rec.execution_date.strftime("%Y-%m-%d") if rec.execution_date else "",
                        "symbol": rec.symbol,
                        "action": rec.action,
                        "quality": quality,
                        "cumulative_avg": round(avg, 3),
                        "count": i + 1,
                    })

                return curve

        except Exception as e:
            logger.error(f"Quality curve computation failed: {e}")
            return []

    def get_quality_summary(self, instance_id: str | None = None) -> dict:
        """Summary statistics for the decision quality dashboard."""
        from src.db.database import get_db
        from src.db.models import DecisionQualityRecord

        try:
            with get_db() as session:
                q = session.query(DecisionQualityRecord)
                if instance_id:
                    q = q.filter(DecisionQualityRecord.instance_id == instance_id)
                records = q.all()

                if not records:
                    return {"total": 0}

                result = {"total": len(records)}
                for horizon in (1, 5, 10, 30):
                    scored = [r for r in records if getattr(r, f"quality_{horizon}d") is not None]
                    if scored:
                        avg_quality = sum(getattr(r, f"quality_{horizon}d") for r in scored) / len(scored)
                        avg_return = sum(getattr(r, f"return_{horizon}d") or 0 for r in scored) / len(scored)
                        avg_spy = sum(getattr(r, f"spy_return_{horizon}d") or 0 for r in scored) / len(scored)
                        result[f"{horizon}d"] = {
                            "count": len(scored),
                            "avg_quality": round(avg_quality, 3),
                            "avg_return": round(avg_return, 2),
                            "avg_spy_return": round(avg_spy, 2),
                            "avg_alpha": round(avg_return - avg_spy, 2),
                        }

                return result

        except Exception as e:
            logger.error(f"Quality summary failed: {e}")
            return {"error": str(e)}

    def _write_quality_summary(self) -> None:
        """Write decision quality summary to JSON."""
        summary = self.get_quality_summary()
        out_path = self.results_dir / "intelligence" / "decision_quality.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            out_path.write_text(json.dumps(summary, indent=2))
        except Exception as e:
            logger.error(f"Failed to write quality summary: {e}")

    def _get_price(self, symbol: str, target_date: datetime) -> float | None:
        """Get closing price near target date."""
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
