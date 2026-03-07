"""Decision Context Builder — assembles track record and learnings at decision time.

This is the core of the compounding intelligence loop. Before any trade decision,
the context builder queries existing data to surface:
- Symbol track record (win rate, avg return, best/worst)
- Setup type performance
- Signal quality ratings
- Prediction history and calibration
- Relevant learnings
- Thesis context

Usage:
    from src.intelligence.context_builder import DecisionContextBuilder
    builder = DecisionContextBuilder()
    ctx = builder.build_context("SLB", setup_type="thesis_driven")
    print(ctx.summary)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.intelligence.setup_types import normalize_setup_type

logger = logging.getLogger(__name__)


@dataclass
class SymbolTrackRecord:
    symbol: str
    total_decisions: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_return_pct: float = 0.0
    avg_hold_days: float = 0.0
    best_trade: dict = field(default_factory=dict)
    worst_trade: dict = field(default_factory=dict)
    last_decisions: list[dict] = field(default_factory=list)


@dataclass
class SetupTypeTrackRecord:
    setup_type: str
    total_decisions: int = 0
    win_rate: float = 0.0
    avg_return_pct: float = 0.0
    sample_adequate: bool = False
    is_best: bool = False
    is_worst: bool = False


@dataclass
class PredictionHistory:
    symbol: str
    total_predictions: int = 0
    accuracy: float = 0.0
    avg_brier: float | None = None
    avg_timing_error_days: float | None = None
    by_type: dict = field(default_factory=dict)


@dataclass
class CalibrationData:
    bins: list[dict] = field(default_factory=list)
    overconfident: bool = False
    calibration_error: float = 0.0
    total_resolved: int = 0


@dataclass
class ThesisContext:
    thesis_id: str = ""
    thesis_name: str = ""
    conviction: float = 0.0
    total_decisions: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    price_targets: dict = field(default_factory=dict)  # symbol -> {bull, base, bear, entry, ...}


@dataclass
class DecisionContext:
    symbol_track_record: SymbolTrackRecord
    setup_type_track_record: SetupTypeTrackRecord | None = None
    relevant_learnings: list[dict] = field(default_factory=list)
    signal_quality: dict = field(default_factory=dict)
    prediction_history: PredictionHistory = field(default_factory=lambda: PredictionHistory(""))
    calibration: CalibrationData = field(default_factory=CalibrationData)
    thesis_context: ThesisContext | None = None
    summary: str = ""


class DecisionContextBuilder:
    """Assembles decision context from existing DB tables."""

    def build_context(
        self,
        symbol: str,
        setup_type: str | None = None,
        thesis_id: str | None = None,
        signal_types: list[str] | None = None,
        scenario: str = "trade_decision",
    ) -> DecisionContext:
        """Build decision context for a symbol.

        Scenarios:
            trade_decision — full context (default)
            morning_briefing — lighter (thesis + overnight predictions)
            eod_review — outcome-focused (scores + learning prompts)
            thesis_review — thesis-focused (conviction + predictions)
        """
        symbol = symbol.upper()

        ctx = DecisionContext(
            symbol_track_record=self._get_symbol_track_record(symbol),
        )

        if setup_type:
            ctx.setup_type_track_record = self._get_setup_type_record(setup_type)

        if scenario in ("trade_decision", "thesis_review"):
            ctx.relevant_learnings = self._get_relevant_learnings(symbol, thesis_id)
            ctx.prediction_history = self._get_prediction_history(symbol)
            ctx.calibration = self._get_calibration_data()

        if scenario in ("trade_decision", "morning_briefing"):
            ctx.signal_quality = self._get_signal_quality(signal_types)

        if thesis_id:
            ctx.thesis_context = self._get_thesis_context(thesis_id)

        ctx.summary = self._format_summary(ctx, symbol, scenario)
        return ctx

    def _get_symbol_track_record(self, symbol: str) -> SymbolTrackRecord:
        """Query DecisionRecord for symbol performance."""
        from src.db.database import get_db
        from src.db.models import DecisionRecord

        record = SymbolTrackRecord(symbol=symbol)

        try:
            with get_db() as session:
                rows = session.query(DecisionRecord).filter(
                    DecisionRecord.symbol == symbol,
                    DecisionRecord.realized_pnl_pct.isnot(None),
                ).order_by(DecisionRecord.timestamp.desc()).all()

                if not rows:
                    return record

                record.total_decisions = len(rows)
                record.wins = sum(1 for r in rows if (r.realized_pnl_pct or 0) > 0)
                record.losses = record.total_decisions - record.wins
                record.win_rate = record.wins / record.total_decisions

                returns = [r.realized_pnl_pct or 0 for r in rows]
                record.avg_return_pct = sum(returns) / len(returns)

                holds = [r.actual_hold_days or r.expected_hold_days or 0 for r in rows]
                record.avg_hold_days = sum(holds) / len(holds) if holds else 0

                best = max(rows, key=lambda r: r.realized_pnl_pct or 0)
                record.best_trade = {
                    "pnl_pct": best.realized_pnl_pct,
                    "date": best.timestamp.strftime("%b %d") if best.timestamp else "",
                    "action": best.action,
                }

                worst = min(rows, key=lambda r: r.realized_pnl_pct or 0)
                record.worst_trade = {
                    "pnl_pct": worst.realized_pnl_pct,
                    "date": worst.timestamp.strftime("%b %d") if worst.timestamp else "",
                    "action": worst.action,
                }

                record.last_decisions = [
                    {
                        "date": r.timestamp.isoformat()[:10] if r.timestamp else "",
                        "action": r.action,
                        "pnl_pct": r.realized_pnl_pct,
                        "setup_type": r.setup_type,
                    }
                    for r in rows[:5]
                ]
        except Exception as e:
            logger.warning(f"Symbol track record query failed: {e}")

        return record

    def _get_setup_type_record(self, setup_type: str) -> SetupTypeTrackRecord:
        """Query DecisionRecord for setup type performance."""
        from src.intelligence.setup_scorer import SetupScorer

        st = normalize_setup_type(setup_type)
        record = SetupTypeTrackRecord(setup_type=st)

        try:
            scorer = SetupScorer()
            perfs = scorer.get_performance_by_type(min_samples=1)
            perf = next((p for p in perfs if p.setup_type == st), None)

            if perf:
                record.total_decisions = perf.total_decisions
                record.win_rate = perf.win_rate
                record.avg_return_pct = perf.avg_return_pct
                record.sample_adequate = perf.sample_adequate

            best = scorer.get_best_setups()
            worst = scorer.get_worst_setups()
            record.is_best = st in best
            record.is_worst = st in worst
        except Exception as e:
            logger.warning(f"Setup type record query failed: {e}")

        return record

    def _get_relevant_learnings(self, symbol: str, thesis_id: str | None = None) -> list[dict]:
        """Query LearningRecord for symbol/thesis-relevant learnings."""
        from src.db.database import get_db
        from src.db.models import LearningRecord

        try:
            with get_db() as session:
                q = session.query(LearningRecord)
                # Get learnings for this symbol OR linked thesis
                conditions = [LearningRecord.symbol == symbol]
                if thesis_id:
                    conditions.append(LearningRecord.thesis_id == thesis_id)

                from sqlalchemy import or_
                rows = q.filter(or_(*conditions)).order_by(
                    LearningRecord.created.desc()
                ).limit(10).all()

                return [
                    {
                        "what_i_learned": r.what_i_learned,
                        "outcome": r.outcome,
                        "pnl_pct": r.pnl_pct,
                        "pattern_name": r.pattern_name,
                        "created": r.created.isoformat()[:10] if r.created else "",
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.warning(f"Learnings query failed: {e}")
            return []

    def _get_signal_quality(self, signal_types: list[str] | None = None) -> dict:
        """Read signal quality from quality.json file."""
        import os
        quality_path = Path(
            os.environ.get("QUANT_RESULTS_DIR", os.path.expanduser("~/quant_results"))
        ) / "signal_quality" / "quality.json"

        if not quality_path.exists():
            return {}

        try:
            data = json.loads(quality_path.read_text())
            if signal_types:
                return {k: v for k, v in data.items() if k in signal_types}
            return data
        except Exception as e:
            logger.warning(f"Signal quality read failed: {e}")
            return {}

    def _get_prediction_history(self, symbol: str) -> PredictionHistory:
        """Query PredictionRecord for symbol prediction accuracy."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord

        history = PredictionHistory(symbol=symbol)

        try:
            with get_db() as session:
                rows = session.query(PredictionRecord).filter(
                    PredictionRecord.symbol == symbol,
                    PredictionRecord.status.in_(["hit", "miss", "expired"]),
                ).all()

                if not rows:
                    return history

                history.total_predictions = len(rows)
                hits = sum(1 for r in rows if r.status == "hit")
                history.accuracy = hits / len(rows)

                briers = [r.brier_score for r in rows if r.brier_score is not None]
                history.avg_brier = sum(briers) / len(briers) if briers else None

                timings = [r.timing_error_days for r in rows if r.timing_error_days is not None]
                history.avg_timing_error_days = sum(timings) / len(timings) if timings else None

                # By type
                by_type: dict[str, dict] = {}
                for r in rows:
                    t = r.prediction_type or "unknown"
                    if t not in by_type:
                        by_type[t] = {"total": 0, "hits": 0}
                    by_type[t]["total"] += 1
                    if r.status == "hit":
                        by_type[t]["hits"] += 1
                history.by_type = by_type
        except Exception as e:
            logger.warning(f"Prediction history query failed: {e}")

        return history

    def _get_calibration_data(self) -> CalibrationData:
        """Compute calibration from all resolved predictions."""
        from src.db.database import get_db
        from src.db.models import PredictionRecord

        cal = CalibrationData()

        try:
            with get_db() as session:
                rows = session.query(PredictionRecord).filter(
                    PredictionRecord.status.in_(["hit", "miss"]),
                    PredictionRecord.confidence.isnot(None),
                ).all()

                if not rows:
                    return cal

                cal.total_resolved = len(rows)

                # Bin by confidence: 0-50, 50-60, 60-70, 70-80, 80-90, 90-100
                bin_edges = [(0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
                for lo, hi in bin_edges:
                    in_bin = [r for r in rows if lo <= (r.confidence or 0) < hi]
                    if not in_bin:
                        continue
                    hits = sum(1 for r in in_bin if r.status == "hit")
                    predicted_avg = sum(r.confidence or 0 for r in in_bin) / len(in_bin)
                    actual_rate = hits / len(in_bin)
                    cal.bins.append({
                        "range": f"{int(lo*100)}-{int(hi*100)}%",
                        "predicted": round(predicted_avg, 3),
                        "actual": round(actual_rate, 3),
                        "n": len(in_bin),
                    })

                # Overall calibration error
                if cal.bins:
                    errors = [abs(b["predicted"] - b["actual"]) for b in cal.bins]
                    cal.calibration_error = round(sum(errors) / len(errors), 3)
                    # Overconfident if predicted > actual on average
                    avg_pred = sum(b["predicted"] * b["n"] for b in cal.bins) / cal.total_resolved
                    avg_actual = sum(b["actual"] * b["n"] for b in cal.bins) / cal.total_resolved
                    cal.overconfident = avg_pred > avg_actual + 0.02
        except Exception as e:
            logger.warning(f"Calibration data query failed: {e}")

        return cal

    def _get_thesis_context(self, thesis_id: str) -> ThesisContext | None:
        """Query thesis record + linked decisions."""
        from src.db.database import get_db
        from src.db.models import ThesisRecord, DecisionRecord

        try:
            with get_db() as session:
                thesis = session.query(ThesisRecord).filter(
                    ThesisRecord.id == thesis_id
                ).first()
                if not thesis:
                    return None

                tc = ThesisContext(
                    thesis_id=thesis_id,
                    thesis_name=thesis.name,
                    conviction=thesis.conviction or 0,
                )

                # Linked decisions with outcomes
                decisions = session.query(DecisionRecord).filter(
                    DecisionRecord.thesis_id == thesis_id,
                    DecisionRecord.realized_pnl_pct.isnot(None),
                ).all()

                tc.total_decisions = len(decisions)
                if decisions:
                    wins = sum(1 for d in decisions if (d.realized_pnl_pct or 0) > 0)
                    tc.win_rate = wins / len(decisions)
                    tc.total_pnl = sum(d.realized_pnl or 0 for d in decisions)

                # Load price targets
                try:
                    pt_raw = thesis.price_targets
                    if pt_raw and isinstance(pt_raw, str):
                        tc.price_targets = json.loads(pt_raw)
                    elif pt_raw and isinstance(pt_raw, dict):
                        tc.price_targets = pt_raw
                except (json.JSONDecodeError, TypeError):
                    pass

                return tc
        except Exception as e:
            logger.warning(f"Thesis context query failed: {e}")
            return None

    def _format_summary(self, ctx: DecisionContext, symbol: str, scenario: str) -> str:
        """Format context into readable text for Claude."""
        lines = [f"=== DECISION CONTEXT: {symbol} ===", ""]

        # Symbol track record
        sr = ctx.symbol_track_record
        if sr.total_decisions > 0:
            lines.append(f"SYMBOL TRACK RECORD ({symbol}):")
            lines.append(f"  {sr.total_decisions} decisions, {sr.win_rate:.0%} win rate, avg return {sr.avg_return_pct:+.1f}%")
            if sr.best_trade:
                lines.append(f"  Best: {sr.best_trade.get('pnl_pct', 0):+.1f}% ({sr.best_trade.get('date', '')})")
            if sr.worst_trade:
                lines.append(f"  Worst: {sr.worst_trade.get('pnl_pct', 0):+.1f}% ({sr.worst_trade.get('date', '')})")
            lines.append("")
        else:
            lines.append(f"SYMBOL TRACK RECORD ({symbol}): No previous decisions")
            lines.append("")

        # Setup type
        st = ctx.setup_type_track_record
        if st and st.total_decisions > 0:
            label = "YOUR BEST SETUP TYPE" if st.is_best else ("WEAK SETUP" if st.is_worst else "")
            lines.append(f"SETUP TYPE ({st.setup_type}):")
            lines.append(f"  {st.total_decisions} decisions, {st.win_rate:.0%} win rate, avg return {st.avg_return_pct:+.1f}%")
            if label:
                lines.append(f"  ** {label} **")
            if not st.sample_adequate:
                lines.append(f"  Note: only {st.total_decisions} samples (need 10+ for reliable stats)")
            lines.append("")

        # Signal quality
        if ctx.signal_quality:
            lines.append("SIGNAL QUALITY (for fired signals):")
            for sig_name, metrics in ctx.signal_quality.items():
                if isinstance(metrics, dict):
                    hr = metrics.get("hit_rate", 0)
                    ic = metrics.get("ic", 0)
                    trend = metrics.get("trend", "stable")
                    lines.append(f"  {sig_name}: {hr:.0%} hit rate ({trend}), IC={ic:.2f}")
            lines.append("")

        # Prediction history
        ph = ctx.prediction_history
        if ph.total_predictions > 0:
            lines.append("PREDICTION HISTORY:")
            lines.append(f"  {ph.total_predictions} predictions on {symbol}, {ph.accuracy:.0%} accurate")
            if ph.avg_timing_error_days is not None:
                lines.append(f"  Your timing averages {ph.avg_timing_error_days:.1f} days off.")
            if ph.avg_brier is not None:
                lines.append(f"  Avg Brier score: {ph.avg_brier:.3f}")
            lines.append("")

        # Calibration
        cal = ctx.calibration
        if cal.total_resolved > 0 and scenario == "trade_decision":
            lines.append("CONFIDENCE CALIBRATION:")
            for b in cal.bins:
                lines.append(f"  When you say {b['range']}, you're right {b['actual']:.0%} of the time (n={b['n']})")
            if cal.overconfident:
                lines.append(f"  ** You are overconfident by ~{cal.calibration_error:.0%}. Discount accordingly. **")
            lines.append("")

        # Relevant learnings
        if ctx.relevant_learnings:
            lines.append("RELEVANT LEARNINGS:")
            for l in ctx.relevant_learnings[:5]:
                outcome_icon = "+" if l.get("outcome") == "win" else "-" if l.get("outcome") == "loss" else "~"
                lines.append(f"  [{outcome_icon}] {l.get('what_i_learned', '')[:100]}")
            lines.append("")

        # Thesis context
        tc = ctx.thesis_context
        if tc:
            lines.append(f"THESIS ({tc.thesis_name}):")
            lines.append(f"  Conviction {tc.conviction:.0f}%, {tc.total_decisions} decisions, {tc.win_rate:.0%} win rate")
            if tc.total_pnl:
                lines.append(f"  Total P&L: ${tc.total_pnl:,.0f}")
            # Price targets
            if tc.price_targets and symbol in tc.price_targets:
                pt = tc.price_targets[symbol]
                lines.append(f"  PRICE TARGETS for {symbol}:")
                lines.append(f"    Bear: ${pt.get('bear_target', 0):.2f}  |  Base: ${pt.get('base_target', 0):.2f}  |  Bull: ${pt.get('bull_target', 0):.2f}")
                entry = pt.get('entry_price', 0)
                if entry > 0:
                    lines.append(f"    Entry: ${entry:.2f}  |  Timeframe: {pt.get('timeframe_days', 90)} days")
                if pt.get('notes'):
                    lines.append(f"    Notes: {pt['notes'][:100]}")
            elif tc.price_targets:
                lines.append(f"  Price targets set for: {', '.join(tc.price_targets.keys())}")
            else:
                lines.append(f"  ** No price targets set — use tracker.set_price_targets() **")
            lines.append("")

        return "\n".join(lines)
