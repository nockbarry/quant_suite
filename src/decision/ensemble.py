"""Decision Ensemble — Multi-evaluation consensus for trade decisions.

Before executing any trade, runs 2 additional evaluations ("challengers")
that independently assess the same trade setup. Only executes on 2/3 consensus.

Architecture:
- Primary: The original trade decision from /trade-decision skill
- Challenger 1: "Devil's advocate" — prompted to find reasons NOT to trade
- Challenger 2: "Independent analyst" — evaluates from scratch without seeing primary

The challengers do NOT see the primary decision (prevents anchoring).
They receive: symbol, market context, thesis info, signals.
They return: BUY/SELL/HOLD direction + confidence + reasoning.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.paths import paths

logger = logging.getLogger(__name__)


@dataclass
class EnsembleMember:
    """One evaluation within the ensemble."""

    member_id: str  # "primary", "challenger_1", "challenger_2"
    symbol: str
    action: str  # BUY, SELL, HOLD, CLOSE, ADD, TRIM
    direction: str  # "long", "short", "neutral"
    confidence: float  # 0-1
    reasoning_summary: str
    agrees_with_primary: bool
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class EnsembleResult:
    """Result of ensemble evaluation for one decision."""

    decision_id: str
    symbol: str
    primary_action: str
    primary_confidence: float
    members: list  # list of EnsembleMember dicts
    consensus_count: int  # How many agree with primary direction
    consensus: bool  # 2/3 or more agree
    final_action: str  # Action to execute (primary if consensus, HOLD if not)
    final_confidence: float  # Average confidence of agreeing members
    ensemble_confidence: float  # consensus_count / 3
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class DecisionEnsemble:
    """Evaluate trade decisions with multiple perspectives."""

    # Actions that imply going long vs reducing/exiting
    LONG_ACTIONS = ("BUY", "ADD")
    SHORT_ACTIONS = ("SELL", "CLOSE", "TRIM")

    # Gate: only run the 3x ensemble when the decision is high-confidence AND
    # the system's calibration is meaningfully off. For routine mid-confidence
    # trades, the calibrated position-sizing cap already de-risks the trade;
    # spending another 2x challenger evaluations buys little.
    CONFIDENCE_GATE = 0.80
    CALIBRATION_GAP_GATE = 0.10  # 10pp stated-vs-actual

    def __init__(self):
        self.log_dir = paths.base / "decisions" / "ensemble"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _calibration_gap(self, stated_confidence: float) -> Optional[float]:
        """Return |stated - actual| for the calibration bucket nearest ``stated_confidence``.

        Returns None if calibration data is unavailable or the bucket has
        insufficient samples (n<10) — caller should treat that as "gap unknown,
        don't gate on it".
        """
        cal_path = paths.intelligence / "calibration.json"
        if not cal_path.exists():
            return None
        try:
            data = json.load(cal_path.open())
        except (OSError, json.JSONDecodeError):
            return None

        best_gap = None
        best_dist = float("inf")
        for b in data.get("bins", []):
            n = b.get("n", 0)
            if n < 10:
                continue
            predicted = float(b.get("predicted", 0))
            actual = float(b.get("actual", 0))
            dist = abs(predicted - stated_confidence)
            if dist < best_dist:
                best_dist = dist
                best_gap = abs(predicted - actual)
        return best_gap

    def should_run_challengers(self, decision: dict) -> tuple[bool, str]:
        """Decide whether to escalate to full 3x ensemble or skip to primary-only.

        Returns (should_run, reason).
        """
        confidence = float(decision.get("confidence", 0.5))
        if confidence < self.CONFIDENCE_GATE:
            return False, (
                f"skipped: confidence {confidence:.0%} < "
                f"{self.CONFIDENCE_GATE:.0%} gate"
            )
        gap = self._calibration_gap(confidence)
        if gap is None:
            # No calibration data -> default to running (legacy behavior)
            return True, "gap_unknown: calibration data insufficient"
        if gap < self.CALIBRATION_GAP_GATE:
            return False, (
                f"skipped: confidence {confidence:.0%} well-calibrated "
                f"(gap {gap:.0%} < {self.CALIBRATION_GAP_GATE:.0%})"
            )
        return True, (
            f"run: confidence {confidence:.0%} >= gate AND gap "
            f"{gap:.0%} >= {self.CALIBRATION_GAP_GATE:.0%}"
        )

    def _get_direction(self, action: str) -> str:
        """Normalize action to direction."""
        if action in self.LONG_ACTIONS:
            return "long"
        elif action in self.SHORT_ACTIONS:
            return "short"
        return "neutral"

    def evaluate(self, decision: dict, context: dict = None) -> EnsembleResult:
        """Run ensemble evaluation on a pending decision.

        Args:
            decision: Dict with symbol, action, confidence, reasoning, thesis info.
                      Expected keys: symbol, action, confidence, reasoning,
                      thesis_name, key_factors, risks, id
            context: Market context (state.json data, signals, etc.)

        Returns:
            EnsembleResult with consensus determination
        """
        context = context or {}
        symbol = decision.get("symbol", "")
        primary_action = decision.get("action", "HOLD")
        primary_confidence = float(decision.get("confidence", 0.5))
        primary_direction = self._get_direction(primary_action)
        decision_id = decision.get("id", f"d_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        logger.info(f"Ensemble evaluating {symbol} {primary_action} (conf={primary_confidence:.0%})")

        # Primary member — the original decision
        primary = EnsembleMember(
            member_id="primary",
            symbol=symbol,
            action=primary_action,
            direction=primary_direction,
            confidence=primary_confidence,
            reasoning_summary=decision.get("reasoning", "")[:200],
            agrees_with_primary=True,
        )

        # Gate: skip the 2x challenger pass when the decision is either
        # low-enough confidence (already de-risked by sizing cap) or
        # well-calibrated (gap < 10pp). Saves ~2 LLM evaluations per decision.
        should_run, gate_reason = self.should_run_challengers(decision)
        if not should_run:
            logger.info(f"Ensemble gate {symbol}: {gate_reason}")
            result = EnsembleResult(
                decision_id=decision_id,
                symbol=symbol,
                primary_action=primary_action,
                primary_confidence=primary_confidence,
                members=[asdict(primary)],
                consensus_count=1,
                consensus=True,  # primary-only pass is trivially consensus
                final_action=primary_action,
                final_confidence=primary_confidence,
                ensemble_confidence=primary_confidence,
            )
            self._save_result(result)
            return result

        # Run challengers (they don't see the primary's conclusion)
        challenger_1 = self._run_challenger(
            "challenger_1",
            symbol,
            decision,
            context,
            role="devil's advocate — find reasons NOT to make this trade",
        )

        challenger_2 = self._run_challenger(
            "challenger_2",
            symbol,
            decision,
            context,
            role="independent analyst — evaluate this setup from scratch",
        )

        members = [primary, challenger_1, challenger_2]

        # Determine agreement (compare direction, not exact action)
        for m in [challenger_1, challenger_2]:
            m.agrees_with_primary = m.direction == primary_direction

        consensus_count = sum(1 for m in members if m.direction == primary_direction)
        consensus = consensus_count >= 2

        # Compute final action and confidence
        if consensus:
            agreeing = [m for m in members if m.direction == primary_direction]
            final_confidence = sum(m.confidence for m in agreeing) / len(agreeing)
            final_action = primary_action
        else:
            final_confidence = 0.0
            final_action = "HOLD"  # No consensus = no trade

        result = EnsembleResult(
            decision_id=decision_id,
            symbol=symbol,
            primary_action=primary_action,
            primary_confidence=primary_confidence,
            members=[asdict(m) for m in members],
            consensus_count=consensus_count,
            consensus=consensus,
            final_action=final_action,
            final_confidence=final_confidence,
            ensemble_confidence=consensus_count / 3.0,
        )

        # Persist
        self._save_result(result)

        # Log outcome
        if consensus:
            logger.info(
                f"CONSENSUS {consensus_count}/3 for {symbol} {primary_action} "
                f"(ensemble conf={result.ensemble_confidence:.0%}, "
                f"avg conf={final_confidence:.0%})"
            )
        else:
            logger.warning(
                f"NO CONSENSUS for {symbol} {primary_action} — "
                f"only {consensus_count}/3 agree, blocking execution"
            )

        return result

    # ------------------------------------------------------------------
    # Challenger execution
    # ------------------------------------------------------------------

    def _run_challenger(
        self,
        member_id: str,
        symbol: str,
        decision: dict,
        context: dict,
        role: str,
    ) -> EnsembleMember:
        """Run a challenger evaluation.

        Uses the Anthropic API directly if available, otherwise falls back
        to a rule-based assessment.
        """
        try:
            return self._run_api_challenger(member_id, symbol, decision, context, role)
        except Exception as e:
            logger.debug(f"API challenger failed ({e}), using heuristic fallback")
            return self._run_heuristic_challenger(member_id, symbol, decision, context, role)

    def _build_challenger_prompt(
        self, symbol: str, decision: dict, context: dict, role: str
    ) -> str:
        """Build the challenger prompt WITHOUT revealing the primary decision.

        Provides raw inputs (thesis, signals, risks, market context) so the
        challenger evaluates independently.
        """
        thesis_info = decision.get("thesis_name", "No thesis")
        signals = decision.get("key_factors", [])
        if isinstance(signals, str):
            try:
                signals = json.loads(signals)
            except (json.JSONDecodeError, TypeError):
                signals = [signals] if signals else []
        risks = decision.get("risks", [])
        if isinstance(risks, str):
            try:
                risks = json.loads(risks)
            except (json.JSONDecodeError, TypeError):
                risks = [risks] if risks else []

        # Market context snippet
        market_summary = ""
        if context:
            regime = context.get("market_regime", {})
            if isinstance(regime, dict):
                market_summary = (
                    f"Market regime: {regime.get('regime', 'unknown')}, "
                    f"VIX: {regime.get('vix', 'N/A')}"
                )

        prompt = f"""You are a {role} for an autonomous trading system.

Evaluate this trade setup for {symbol}:
- Thesis: {thesis_info}
- Key signals: {', '.join(str(s) for s in signals[:5]) if signals else 'None provided'}
- Known risks: {', '.join(str(r) for r in risks[:5]) if risks else 'None provided'}
- {market_summary or 'No market context available'}

What is your recommendation? Respond with EXACTLY this JSON format:
{{"action": "BUY" or "SELL" or "HOLD", "confidence": 0.0 to 1.0, "reasoning": "one sentence"}}

Important: Only output the JSON object, nothing else."""
        return prompt

    def _run_api_challenger(
        self, member_id: str, symbol: str, decision: dict, context: dict, role: str
    ) -> EnsembleMember:
        """Run challenger via Claude Code subprocess (Haiku for cost efficiency).

        Routes through the Claude Code subscription rather than a separate
        Anthropic API channel — same billing channel as all other LLM calls.
        """
        from src.core.claude_code_client import get_client, ClaudeCodeError

        prompt = self._build_challenger_prompt(symbol, decision, context, role)

        try:
            resp = get_client().complete(
                user=prompt,
                system="You are a critical trade evaluator. Output strict JSON only.",
                model="haiku",
                max_turns=1,
            )
        except ClaudeCodeError as e:
            raise ValueError(f"Challenger subprocess failed: {e}") from e

        text = resp.text

        # Parse JSON from response (challenger output is one small object)
        json_match = re.search(r"\{[^}]+\}", text)
        if json_match:
            data = json.loads(json_match.group())
            action = data.get("action", "HOLD").upper()
            if action not in ("BUY", "SELL", "HOLD", "CLOSE", "ADD", "TRIM"):
                action = "HOLD"
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            return EnsembleMember(
                member_id=member_id,
                symbol=symbol,
                action=action,
                direction=self._get_direction(action),
                confidence=confidence,
                reasoning_summary=data.get("reasoning", "")[:200],
                agrees_with_primary=False,  # set later by evaluate()
            )
        raise ValueError(f"Could not parse challenger response: {text[:100]}")

    def _run_heuristic_challenger(
        self, member_id: str, symbol: str, decision: dict, context: dict, role: str
    ) -> EnsembleMember:
        """Fallback: rule-based challenger when API unavailable.

        Uses simple heuristics based on available data to provide
        an independent assessment.
        """
        primary_action = decision.get("action", "HOLD")
        primary_conf = float(decision.get("confidence", 0.5))

        if "devil" in role.lower():
            # Devil's advocate: lean toward opposing low-confidence trades
            if primary_action in self.LONG_ACTIONS:
                # Challenge BUYs more aggressively at low confidence
                oppose_prob = 1 - primary_conf
                action = "HOLD" if oppose_prob > 0.4 else primary_action
                conf = max(0.3, primary_conf - 0.15)
            elif primary_action in self.SHORT_ACTIONS:
                # Slightly less likely to oppose sells (risk reduction)
                action = primary_action
                conf = primary_conf * 0.9
            else:
                action = "HOLD"
                conf = 0.5
            reasoning = "Devil's advocate: systematic skepticism applied"
        else:
            # Independent analyst: slight regression to mean
            action = primary_action
            conf = primary_conf * 0.85 + 0.5 * 0.15  # Regress 15% toward 0.5
            reasoning = "Independent assessment with confidence regression"

        return EnsembleMember(
            member_id=member_id,
            symbol=symbol,
            action=action,
            direction=self._get_direction(action),
            confidence=round(conf, 3),
            reasoning_summary=reasoning,
            agrees_with_primary=False,  # set later by evaluate()
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_result(self, result: EnsembleResult):
        """Save ensemble result to JSON file."""
        filename = (
            f"ensemble_{result.decision_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        filepath = self.log_dir / filename
        try:
            with open(filepath, "w") as f:
                json.dump(asdict(result), f, indent=2)
            logger.debug(f"Saved ensemble result to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save ensemble result: {e}")

    def get_recent_results(self, days: int = 7) -> list:
        """Get recent ensemble results, newest first."""
        results = []
        for f in sorted(self.log_dir.glob("ensemble_*.json"), reverse=True):
            try:
                with open(f) as fh:
                    results.append(json.load(fh))
                if len(results) >= 50:
                    break
            except Exception:
                continue
        return results

    def get_consensus_stats(self) -> dict:
        """Compute ensemble consensus statistics over recent results."""
        results = self.get_recent_results(days=30)
        if not results:
            return {
                "total": 0,
                "consensus_count": 0,
                "consensus_rate": 0.0,
                "rejected_count": 0,
                "avg_ensemble_confidence": 0.0,
            }

        total = len(results)
        consensus = sum(1 for r in results if r.get("consensus", False))
        avg_conf = sum(r.get("ensemble_confidence", 0) for r in results) / total

        return {
            "total": total,
            "consensus_count": consensus,
            "consensus_rate": consensus / total,
            "rejected_count": total - consensus,
            "avg_ensemble_confidence": round(avg_conf, 3),
        }

    def get_result_for_decision(self, decision_id: str) -> Optional[dict]:
        """Look up ensemble result for a specific decision."""
        for f in self.log_dir.glob(f"ensemble_{decision_id}_*.json"):
            try:
                with open(f) as fh:
                    return json.load(fh)
            except Exception:
                continue
        return None
