#!/usr/bin/env python3
"""Automated Corrections Engine.

Reads alerts from cross-reference engine, stress tester, and meta-observer,
then applies mechanical corrections:

1. Insider Divergence RED FLAG -> reduce thesis conviction by 10%, log reason
2. Regulatory Ceiling -> freeze position (set "frozen" note on thesis)
3. Failed Intervention (bullish) -> increase thesis conviction by 5%
4. Concentration breach (from stress test) -> queue trim decision
5. Gold/sector cap breach -> queue trim (like rules engine)
6. Thesis prediction accuracy < 25% for 10+ predictions -> auto-invalidate thesis

Runs every 30 minutes alongside cross-reference engine.
No Claude tokens -- pure Python.
"""

import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

# Ensure project root is on sys.path when run as script
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.core.paths import paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [auto-correct] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class CorrectionAction:
    """A correction applied by the engine."""

    timestamp: str
    action_type: str  # conviction_change, position_freeze, thesis_invalidate, trim_queue, conviction_exit
    symbol: str
    thesis_id: str
    thesis_name: str
    old_value: float  # old conviction or position size
    new_value: float  # new conviction or position size
    reason: str
    source_alert: str  # which alert triggered this
    applied: bool


class AutoCorrectionEngine:
    """Applies mechanical corrections from system alerts."""

    CORRECTION_LOG = paths.logs / "auto_corrections.jsonl"
    TRIM_QUEUE = paths.scheduler / "trim_queue.json"
    COOLDOWN_HOURS = 24  # Don't apply same correction type+thesis within 24h

    def __init__(self):
        self.corrections: list[CorrectionAction] = []
        self.recent_corrections = self._load_recent_corrections()

    def _load_recent_corrections(self) -> list[dict]:
        """Load corrections from last 24h to avoid duplicates."""
        if not self.CORRECTION_LOG.exists():
            return []

        cutoff = datetime.now() - timedelta(hours=self.COOLDOWN_HOURS)
        recent = []
        try:
            with open(self.CORRECTION_LOG) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry.get("timestamp", ""))
                        if ts >= cutoff and entry.get("applied", False):
                            recent.append(entry)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception as e:
            logger.warning(f"Failed to load recent corrections: {e}")
        return recent

    def _in_cooldown(self, action_type: str, thesis_id: str, symbol: str = "") -> bool:
        """Check if this correction was already applied recently.

        For portfolio-level trims, include ``symbol`` in the key so a breach on
        one sector doesn't silence a breach on a different sector. For thesis-
        level corrections, keep the legacy (action_type, thesis_id) key.
        """
        key_with_symbol = action_type == "trim_queue" and thesis_id == "portfolio_level"
        for entry in self.recent_corrections:
            if (
                entry.get("action_type") == action_type
                and entry.get("thesis_id") == thesis_id
            ):
                if key_with_symbol and entry.get("symbol") != symbol:
                    continue
                return True
        return False

    def run(self) -> list[CorrectionAction]:
        """Run all correction checks and apply."""
        corrections: list[CorrectionAction] = []
        corrections.extend(self._process_cross_reference_alerts())
        corrections.extend(self._process_stress_test())
        corrections.extend(self._process_prediction_accuracy())
        corrections.extend(self._process_conviction_exits())

        # Apply corrections
        applied_count = 0
        skipped_count = 0
        for c in corrections:
            if not self._in_cooldown(c.action_type, c.thesis_id, c.symbol):
                self._apply_correction(c)
                c.applied = True
                applied_count += 1
            else:
                c.applied = False
                skipped_count += 1
                logger.info(f"Skipped (cooldown): {c.action_type} on {c.thesis_name}")

        # Log all corrections
        self._log_corrections(corrections)

        if corrections:
            logger.info(
                f"Auto-corrections: {len(corrections)} generated, "
                f"{applied_count} applied, {skipped_count} skipped (cooldown)"
            )
        else:
            logger.info("Auto-corrections: no corrections needed")

        return corrections

    def _process_cross_reference_alerts(self) -> list[CorrectionAction]:
        """Read cross-reference alerts and generate corrections.

        Rules:
        - insider_divergence (red_flag) -> reduce thesis conviction by 10%
        - regulatory_ceiling (warning/red_flag) -> add REGULATORY_CEILING note to thesis
        - failed_intervention with bullish reaction -> increase conviction by 5%
        """
        alerts_file = paths.live / "cross_reference_alerts.json"
        if not alerts_file.exists():
            logger.debug("No cross_reference_alerts.json found")
            return []

        try:
            with open(alerts_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read cross-reference alerts: {e}")
            return []

        corrections = []
        now = datetime.now().isoformat()

        for alert in data.get("alerts", []):
            alert_type = alert.get("alert_type", "")
            severity = alert.get("severity", "")
            symbols = alert.get("symbols", [])
            alert_id = alert.get("alert_id", "unknown")
            title = alert.get("title", "")

            # Only process alerts from the last 2 hours (avoid re-processing old ones)
            alert_ts = alert.get("timestamp", "")
            if alert_ts:
                try:
                    alert_time = datetime.fromisoformat(alert_ts)
                    if datetime.now() - alert_time > timedelta(hours=2):
                        continue
                except (ValueError, TypeError):
                    pass

            if alert_type == "insider_divergence" and severity == "red_flag":
                for sym in symbols:
                    thesis = self._find_thesis_for_symbol(sym)
                    if thesis:
                        corrections.append(CorrectionAction(
                            timestamp=now,
                            action_type="conviction_change",
                            symbol=sym,
                            thesis_id=thesis.id,
                            thesis_name=thesis.name,
                            old_value=thesis.conviction,
                            new_value=max(15, thesis.conviction - 10),
                            reason=f"Insider divergence red flag: {title}",
                            source_alert=alert_id,
                            applied=False,
                        ))

            elif alert_type == "regulatory_ceiling" and severity in ("warning", "red_flag"):
                for sym in symbols:
                    thesis = self._find_thesis_for_symbol(sym)
                    if thesis:
                        corrections.append(CorrectionAction(
                            timestamp=now,
                            action_type="position_freeze",
                            symbol=sym,
                            thesis_id=thesis.id,
                            thesis_name=thesis.name,
                            old_value=thesis.conviction,
                            new_value=thesis.conviction,  # No conviction change, just freeze
                            reason=f"Regulatory ceiling: {title}. DO NOT ADD.",
                            source_alert=alert_id,
                            applied=False,
                        ))

            elif alert_type == "failed_intervention":
                # Failed bearish intervention = bullish signal
                reaction = alert.get("evidence", {}).get("reaction", "")
                if reaction in ("rejected", ""):
                    for sym in symbols:
                        thesis = self._find_thesis_for_symbol(sym)
                        if thesis:
                            corrections.append(CorrectionAction(
                                timestamp=now,
                                action_type="conviction_change",
                                symbol=sym,
                                thesis_id=thesis.id,
                                thesis_name=thesis.name,
                                old_value=thesis.conviction,
                                new_value=min(100, thesis.conviction + 5),
                                reason=f"Failed intervention (bullish): {title}",
                                source_alert=alert_id,
                                applied=False,
                            ))

        return corrections

    def _process_stress_test(self) -> list[CorrectionAction]:
        """Read stress test and generate corrections for breaches.

        If concentration_risk_score > 0.5 or max_single_position_pct > 15%,
        queue a trim on the largest position/thesis.
        """
        report_file = paths.risk_reports / "stress_test_latest.json"
        if not report_file.exists():
            logger.debug("No stress_test_latest.json found")
            return []

        try:
            with open(report_file) as f:
                report = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read stress test report: {e}")
            return []

        corrections = []
        now = datetime.now().isoformat()

        # Check if report is fresh (within last 24h)
        report_ts = report.get("timestamp", "")
        if report_ts:
            try:
                report_time = datetime.fromisoformat(report_ts)
                if datetime.now() - report_time > timedelta(hours=24):
                    logger.debug("Stress test report is stale (>24h), skipping")
                    return []
            except (ValueError, TypeError):
                pass

        concentration_score = report.get("concentration_risk_score", 0)
        max_position_pct = report.get("max_single_position_pct", 0)
        max_sector_pct = report.get("max_single_sector_exposure_pct", 0)
        sector_weights = report.get("sector_weights", {})

        # Concentration breach: HHI > 0.5
        if concentration_score > 0.5:
            # Find the largest sector to trim
            if sector_weights:
                largest_sector = max(sector_weights, key=sector_weights.get)
                largest_pct = sector_weights[largest_sector]
                corrections.append(CorrectionAction(
                    timestamp=now,
                    action_type="trim_queue",
                    symbol=largest_sector,
                    thesis_id="portfolio_level",
                    thesis_name=f"Sector: {largest_sector}",
                    old_value=largest_pct,
                    new_value=40.0,  # Target max sector weight
                    reason=(
                        f"Concentration risk score {concentration_score:.2f} > 0.5 threshold. "
                        f"Largest sector {largest_sector} at {largest_pct:.1f}%"
                    ),
                    source_alert="stress_test",
                    applied=False,
                ))

        # Max position breach: > 15%
        if max_position_pct > 15:
            corrections.append(CorrectionAction(
                timestamp=now,
                action_type="trim_queue",
                symbol="largest_position",
                thesis_id="portfolio_level",
                thesis_name="Position sizing breach",
                old_value=max_position_pct,
                new_value=10.0,  # Target max position weight
                reason=f"Max position at {max_position_pct:.1f}% exceeds 15% limit",
                source_alert="stress_test",
                applied=False,
            ))

        # Sector cap breach: any sector > 45%
        for sector, weight in sector_weights.items():
            if weight > 45:
                corrections.append(CorrectionAction(
                    timestamp=now,
                    action_type="trim_queue",
                    symbol=sector,
                    thesis_id="portfolio_level",
                    thesis_name=f"Sector cap: {sector}",
                    old_value=weight,
                    new_value=40.0,
                    reason=f"Sector {sector} at {weight:.1f}% exceeds 45% cap",
                    source_alert="stress_test",
                    applied=False,
                ))

        return corrections

    def _process_prediction_accuracy(self) -> list[CorrectionAction]:
        """Auto-invalidate theses with < 25% prediction accuracy over 10+ predictions.

        Read from belief updater daily reports for thesis accuracy data.
        """
        corrections = []
        now = datetime.now().isoformat()

        # Find the latest belief update report
        intel_dir = paths.intelligence
        if not intel_dir.exists():
            return []

        daily_updates = sorted(intel_dir.glob("daily_update_*.json"), reverse=True)
        if not daily_updates:
            logger.debug("No daily update reports found")
            return []

        latest_report_path = daily_updates[0]
        try:
            with open(latest_report_path) as f:
                report = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read belief update report: {e}")
            return []

        # Check thesis suggestions for low-accuracy theses
        for suggestion in report.get("thesis_suggestions", []):
            accuracy = suggestion.get("prediction_accuracy", 1.0)
            count = suggestion.get("prediction_count", 0)
            thesis_id = suggestion.get("thesis_id", "")
            thesis_name = suggestion.get("thesis_name", "")

            if count >= 20 and accuracy < 0.25:
                # Verify thesis is still active and above invalidation threshold
                thesis = self._get_thesis_by_id(thesis_id)
                if thesis and thesis.status == "active" and thesis.conviction > 15:
                    # Earnings-beat veto: skip if a manual override was applied within 14 days.
                    # Prediction accuracy for secondary proxies (e.g., food/insurance predictions)
                    # should not invalidate a thesis where the primary vehicle just beat earnings.
                    veto_keywords = ("veto", "beat", "override", "manual", "earnings")
                    veto_cutoff = datetime.now() - timedelta(days=14)

                    def _h_reason(h) -> str:
                        return (h.get("reason", "") if isinstance(h, dict) else getattr(h, "reason", "")).lower()

                    def _h_ts(h):
                        raw = h.get("timestamp") if isinstance(h, dict) else getattr(h, "timestamp", None)
                        if isinstance(raw, str):
                            try:
                                return datetime.fromisoformat(raw)
                            except ValueError:
                                return datetime.min
                        return raw if isinstance(raw, datetime) else datetime.min

                    recent_manual = any(
                        any(kw in _h_reason(h) for kw in veto_keywords)
                        and _h_ts(h) > veto_cutoff
                        for h in getattr(thesis, "conviction_history", [])
                    )
                    if recent_manual:
                        logger.info(
                            f"Auto-invalidation vetoed for '{thesis_name}': "
                            f"manual earnings-beat override within 14 days"
                        )
                        continue
                    corrections.append(CorrectionAction(
                        timestamp=now,
                        action_type="thesis_invalidate",
                        symbol="",
                        thesis_id=thesis_id,
                        thesis_name=thesis_name,
                        old_value=thesis.conviction,
                        new_value=15,
                        reason=(
                            f"Prediction accuracy {accuracy:.0%} < 25% threshold "
                            f"over {count} predictions"
                        ),
                        source_alert=f"belief_update:{latest_report_path.name}",
                        applied=False,
                    ))

        return corrections

    def _process_conviction_exits(self) -> list[CorrectionAction]:
        """Queue close-trim for every position linked to a thesis with conviction <40%.

        The belief updater drops conviction and adaptive triggers spawn a
        /trade-decision session, but nothing was mechanically closing the
        positions. This fills the gap: we queue a target_pct=0 trim per linked
        position so the trade-decision session (and operator) have an
        actionable surface.
        """
        corrections: list[CorrectionAction] = []
        now = datetime.now().isoformat()

        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
            theses = tracker.get_all_theses()
        except Exception as e:
            logger.warning(f"conviction_exit: failed to load theses: {e}")
            return []

        for thesis in theses:
            if getattr(thesis, "status", "") != "active":
                continue
            conviction = getattr(thesis, "conviction", 100)
            if conviction >= 40:
                continue

            positions = getattr(thesis, "positions", []) or []
            if not positions:
                continue

            for sym in positions:
                corrections.append(CorrectionAction(
                    timestamp=now,
                    action_type="conviction_exit",
                    symbol=sym,
                    thesis_id=thesis.id,
                    thesis_name=thesis.name,
                    old_value=conviction,
                    new_value=0.0,
                    reason=(
                        f"Conviction {conviction:.0f}% < 40% threshold. "
                        f"Auto-queued close of {sym}."
                    ),
                    source_alert="belief_updater",
                    applied=False,
                ))

        return corrections

    def _find_thesis_for_symbol(self, symbol: str):
        """Find the first active thesis that contains this symbol."""
        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
            theses = tracker.get_theses_for_symbol(symbol)
            return theses[0] if theses else None
        except Exception as e:
            logger.warning(f"Failed to find thesis for {symbol}: {e}")
            return None

    def _get_thesis_by_id(self, thesis_id: str):
        """Get a thesis by its ID."""
        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
            return tracker.get_thesis(thesis_id)
        except Exception as e:
            logger.warning(f"Failed to get thesis {thesis_id}: {e}")
            return None

    def _apply_correction(self, correction: CorrectionAction):
        """Apply a single correction."""
        try:
            from src.knowledge.thesis import ThesisTracker
            tracker = ThesisTracker(paths.theses)
        except Exception as e:
            logger.error(f"Failed to initialize ThesisTracker: {e}")
            return

        if correction.action_type == "conviction_change":
            thesis = tracker.get_thesis(correction.thesis_id)
            if thesis and thesis.status == "active":
                thesis.update_conviction(
                    correction.new_value,
                    f"[AUTO-CORRECTION] {correction.reason}",
                )
                tracker._save_thesis(thesis)
                logger.info(
                    f"Applied: {correction.thesis_name} conviction "
                    f"{correction.old_value:.0f}% -> {correction.new_value:.0f}%"
                )
            else:
                logger.info(
                    f"Skipped conviction change for {correction.thesis_name}: "
                    f"thesis not found or not active"
                )

        elif correction.action_type == "position_freeze":
            thesis = tracker.get_thesis(correction.thesis_id)
            if thesis:
                note = (
                    f"FROZEN: {correction.reason}"
                )
                thesis.add_note(note)
                tracker._save_thesis(thesis)
                logger.info(f"Frozen: {correction.thesis_name} -- {correction.reason}")
            else:
                logger.info(f"Skipped freeze for {correction.thesis_name}: thesis not found")

        elif correction.action_type == "thesis_invalidate":
            thesis = tracker.get_thesis(correction.thesis_id)
            if thesis and thesis.conviction > 15:
                thesis.update_conviction(
                    15,
                    f"[AUTO-INVALIDATION] {correction.reason}",
                )
                tracker._save_thesis(thesis)
                logger.info(f"Invalidated: {correction.thesis_name}")

                # Also push to situation board so other sessions know
                try:
                    from src.swarm.situation_board import SituationBoard
                    board = SituationBoard.load_or_create()
                    board.add_observation(
                        source="auto_corrections",
                        obs_type="alert",
                        text=(
                            f"THESIS AUTO-INVALIDATED: {correction.thesis_name} "
                            f"({correction.reason})"
                        ),
                        symbols=thesis.positions[:5] if thesis.positions else [],
                    )
                    board.save()
                except Exception as e:
                    logger.warning(f"Failed to push invalidation to situation board: {e}")
            else:
                logger.info(
                    f"Skipped invalidation for {correction.thesis_name}: "
                    f"thesis not found or already at minimum conviction"
                )

        elif correction.action_type == "trim_queue":
            # Queue the trim for the next trade-decision session to action
            self._queue_trim(correction)
            logger.info(
                f"Queued trim: {correction.thesis_name} "
                f"({correction.old_value:.1f}% -> target {correction.new_value:.1f}%)"
            )

        elif correction.action_type == "conviction_exit":
            # Queue close-trim for this specific position linked to a
            # sub-threshold-conviction thesis.
            self._queue_trim(correction)
            logger.info(
                f"Queued conviction-exit close: {correction.symbol} "
                f"(thesis '{correction.thesis_name}' conviction {correction.old_value:.0f}%)"
            )

        # Audit trail via ProcessEvent
        try:
            from src.autonomy.provenance import log_event
            log_event(
                "auto_correction_applied",
                source="auto_corrections",
                title=(
                    f"{correction.action_type}: {correction.thesis_name} "
                    f"({correction.reason[:80]})"
                ),
            )
        except Exception:
            pass

    def _queue_trim(self, correction: CorrectionAction):
        """Write trim request to trim_queue.json for trade-decision to consume."""
        queue = []
        if self.TRIM_QUEUE.exists():
            try:
                with open(self.TRIM_QUEUE) as f:
                    queue = json.load(f)
                if not isinstance(queue, list):
                    queue = []
            except (json.JSONDecodeError, OSError):
                queue = []

        queue.append({
            "timestamp": correction.timestamp,
            "symbol": correction.symbol,
            "thesis_name": correction.thesis_name,
            "current_pct": correction.old_value,
            "target_pct": correction.new_value,
            "reason": correction.reason,
            "source": "auto_corrections",
        })

        self.TRIM_QUEUE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.TRIM_QUEUE, "w") as f:
                json.dump(queue, f, indent=2)
        except OSError as e:
            logger.error(f"Failed to write trim queue: {e}")

        try:
            from src.swarm.situation_board import SituationBoard
            board = SituationBoard.load_or_create()
            board.add_observation(
                source="auto_corrections",
                obs_type="alert",
                text=(
                    f"TRIM QUEUED: {correction.thesis_name} "
                    f"{correction.old_value:.1f}% -> target {correction.new_value:.1f}% "
                    f"({correction.reason[:80]})"
                ),
                symbols=[correction.symbol] if correction.symbol else [],
            )
            board.save()
        except Exception as e:
            logger.warning(f"Failed to surface trim to situation board: {e}")

    def _log_corrections(self, corrections: list[CorrectionAction]):
        """Append corrections to JSONL log."""
        if not corrections:
            return
        self.CORRECTION_LOG.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.CORRECTION_LOG, "a") as f:
                for c in corrections:
                    f.write(json.dumps(asdict(c)) + "\n")
        except OSError as e:
            logger.error(f"Failed to write correction log: {e}")


def main():
    """Run the auto-correction engine."""
    logger.info("Starting auto-correction engine")
    engine = AutoCorrectionEngine()
    corrections = engine.run()

    # Summary
    applied = [c for c in corrections if c.applied]
    if applied:
        print(f"\nApplied {len(applied)} corrections:")
        for c in applied:
            print(f"  [{c.action_type}] {c.thesis_name}: {c.reason[:80]}")
    else:
        print("No corrections applied.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
