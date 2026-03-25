"""Strategic Context — multi-day persistent memory for the Athena swarm.

Maintained primarily by the Reviewer (internal-review) and Theorist agents.
Read by morning-briefing, trade-decision, analyst, and researcher sessions.

Unlike the situation board (resets daily), this persists across days and tracks:
- Thesis conviction momentum (rolling 7-day windows)
- Developing multi-day patterns
- Signal source quality trends
- Upcoming catalysts with scenarios
- Research hypotheses to test
- Open strategic questions

File: ~/quant_results/scheduler/strategic_context.json
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from src.core.paths import paths

logger = logging.getLogger(__name__)

CONTEXT_PATH = paths.base / "scheduler" / "strategic_context.json"

MOMENTUM_WINDOW = 7  # Days of conviction history to keep
MAX_PATTERNS = 20
MAX_HYPOTHESES = 20
MAX_CATALYSTS = 30
MAX_QUESTIONS = 15


def _empty_context() -> dict:
    """Create a fresh strategic context."""
    return {
        "last_updated": datetime.now().isoformat(),
        "updated_by": "system",
        "developing_patterns": [],
        "thesis_momentum": {},
        "signal_source_trends": {},
        "upcoming_catalysts": [],
        "research_hypotheses": [],
        "open_questions": [],
    }


class StrategicContext:
    """Multi-day persistent memory maintained by Reviewer/Theorist.

    Usage:
        ctx = StrategicContext.load()
        ctx.update_thesis_momentum("Iran War Energy", 95)
        ctx.add_catalyst("2026-03-18", "MU Earnings", ["MU", "SOXX"], "HBM raise", "Inventory build")
        ctx.save()
    """

    def __init__(self, data: dict):
        self.data = data

    @classmethod
    def load(cls) -> "StrategicContext":
        """Load strategic context (never auto-resets — multi-day persistent)."""
        if not CONTEXT_PATH.exists():
            return cls(_empty_context())

        try:
            with open(CONTEXT_PATH) as f:
                data = json.load(f)
            return cls(data)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error loading strategic context: {e}")
            return cls(_empty_context())

    def update_thesis_momentum(self, thesis_name: str, conviction: float):
        """Track thesis conviction trend (rolling 7-day window).

        Args:
            thesis_name: Name of the thesis
            conviction: Current conviction percentage (0-100)
        """
        momentum = self.data.setdefault("thesis_momentum", {})
        entry = momentum.setdefault(thesis_name, {
            "conviction_history": [],
            "trend": "unknown",
        })

        today = datetime.now().strftime("%Y-%m-%d")
        history = entry.get("conviction_history", [])

        # Update today's entry or append
        updated = False
        for item in history:
            if item.get("date") == today:
                item["conviction"] = conviction
                updated = True
                break
        if not updated:
            history.append({"date": today, "conviction": conviction})

        # Keep only last MOMENTUM_WINDOW days
        history = history[-MOMENTUM_WINDOW:]
        entry["conviction_history"] = history

        # Calculate trend
        if len(history) >= 2:
            values = [h["conviction"] for h in history]
            first_half = sum(values[:len(values)//2]) / max(len(values)//2, 1)
            second_half = sum(values[len(values)//2:]) / max(len(values) - len(values)//2, 1)
            diff = second_half - first_half

            if diff > 5:
                entry["trend"] = "rising"
            elif diff < -5:
                entry["trend"] = "declining"
            else:
                if values[-1] >= 80:
                    entry["trend"] = "stable_high"
                elif values[-1] <= 30:
                    entry["trend"] = "stable_low"
                else:
                    entry["trend"] = "stable"
        else:
            entry["trend"] = "new"

        momentum[thesis_name] = entry

    def add_developing_pattern(
        self,
        name: str,
        evidence: str,
        interpretation: str,
        affected_theses: list[str] | None = None,
        action_suggestion: str | None = None,
    ):
        """Record a developing multi-day pattern.

        Args:
            name: Short descriptive name
            evidence: What evidence supports this pattern
            interpretation: What it means
            affected_theses: Which theses are affected
            action_suggestion: What to do about it
        """
        patterns = self.data.setdefault("developing_patterns", [])

        # Check if pattern already exists (by name)
        for p in patterns:
            if p.get("name") == name:
                # Update existing
                p["evidence"].append(f"{datetime.now().strftime('%m/%d')}: {evidence}")
                p["evidence"] = p["evidence"][-10:]  # Keep last 10
                p["interpretation"] = interpretation
                p["days_active"] = (
                    datetime.now() - datetime.fromisoformat(p["first_observed"])
                ).days
                if action_suggestion:
                    p["action_suggestion"] = action_suggestion
                return

        # New pattern
        pattern = {
            "id": f"dp_{len(patterns) + 1:03d}",
            "name": name,
            "first_observed": datetime.now().strftime("%Y-%m-%d"),
            "days_active": 0,
            "evidence": [f"{datetime.now().strftime('%m/%d')}: {evidence}"],
            "interpretation": interpretation,
            "affected_theses": affected_theses or [],
        }
        if action_suggestion:
            pattern["action_suggestion"] = action_suggestion

        patterns.append(pattern)

        # Trim to max
        if len(patterns) > MAX_PATTERNS:
            self.data["developing_patterns"] = patterns[-MAX_PATTERNS:]

    def update_signal_source_trend(self, source: str, hit_rate: float):
        """Update signal source quality trends.

        Args:
            source: Source name (congressional, wsb, insider, etc.)
            hit_rate: Current hit rate (0.0-1.0)
        """
        trends = self.data.setdefault("signal_source_trends", {})
        entry = trends.setdefault(source, {
            "hit_rate_history": [],
            "trend": "unknown",
        })

        today = datetime.now().strftime("%Y-%m-%d")
        history = entry.get("hit_rate_history", [])

        # Update or append
        updated = False
        for item in history:
            if item.get("date") == today:
                item["hit_rate"] = round(hit_rate, 3)
                updated = True
                break
        if not updated:
            history.append({"date": today, "hit_rate": round(hit_rate, 3)})

        history = history[-30:]  # Keep 30 days
        entry["hit_rate_history"] = history

        # Compute rolling averages
        rates = [h["hit_rate"] for h in history]
        entry["hit_rate_30d"] = round(sum(rates) / len(rates), 3) if rates else 0
        recent = rates[-7:] if len(rates) >= 7 else rates
        entry["hit_rate_7d"] = round(sum(recent) / len(recent), 3) if recent else 0

        # Trend
        if entry["hit_rate_7d"] > entry["hit_rate_30d"] + 0.05:
            entry["trend"] = "improving"
        elif entry["hit_rate_7d"] < entry["hit_rate_30d"] - 0.05:
            entry["trend"] = "declining"
        else:
            entry["trend"] = "stable"

        trends[source] = entry

    def add_catalyst(
        self,
        date: str,
        event: str,
        affected: list[str],
        scenario_bull: str,
        scenario_bear: str,
    ):
        """Add upcoming catalyst with bull/bear scenarios.

        Args:
            date: Expected date (YYYY-MM-DD)
            event: Event description
            affected: Affected symbols
            scenario_bull: Bull case description
            scenario_bear: Bear case description
        """
        catalysts = self.data.setdefault("upcoming_catalysts", [])

        # Check for duplicate
        for c in catalysts:
            if c.get("date") == date and c.get("event") == event:
                c["affected"] = affected
                c["scenario_bull"] = scenario_bull
                c["scenario_bear"] = scenario_bear
                return

        catalysts.append({
            "date": date,
            "event": event,
            "affected": affected,
            "scenario_bull": scenario_bull,
            "scenario_bear": scenario_bear,
        })

        # Sort by date and trim
        catalysts.sort(key=lambda c: c.get("date", ""))
        # Remove past catalysts (keep 3 days of history for review)
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        catalysts = [c for c in catalysts if c.get("date", "") >= cutoff]
        self.data["upcoming_catalysts"] = catalysts[:MAX_CATALYSTS]

    def add_research_hypothesis(
        self,
        hypothesis: str,
        suggested_by: str,
        test_plan: str | None = None,
    ):
        """Add a hypothesis for the researcher to test.

        Args:
            hypothesis: What to test
            suggested_by: Who/what suggested it
            test_plan: How to test it (optional)
        """
        hypotheses = self.data.setdefault("research_hypotheses", [])

        # Check for duplicate (fuzzy — same first 50 chars)
        for h in hypotheses:
            if h.get("hypothesis", "")[:50] == hypothesis[:50]:
                return

        hypotheses.append({
            "id": f"h_{len(hypotheses) + 1:03d}",
            "hypothesis": hypothesis,
            "status": "untested",
            "suggested_by": suggested_by,
            "suggested_date": datetime.now().strftime("%Y-%m-%d"),
            "test_plan": test_plan,
        })

        if len(hypotheses) > MAX_HYPOTHESES:
            # Remove tested ones first, then oldest untested
            tested = [h for h in hypotheses if h["status"] != "untested"]
            untested = [h for h in hypotheses if h["status"] == "untested"]
            self.data["research_hypotheses"] = (
                untested[-MAX_HYPOTHESES:] if len(untested) > MAX_HYPOTHESES
                else untested + tested[-(MAX_HYPOTHESES - len(untested)):]
            )

    def update_hypothesis_status(self, hypothesis_id: str, status: str, finding: str | None = None):
        """Update a research hypothesis status.

        Args:
            hypothesis_id: The hypothesis ID (e.g. "h_001")
            status: New status (untested, partially_tested, tested, confirmed, rejected)
            finding: What was found (optional)
        """
        for h in self.data.get("research_hypotheses", []):
            if h.get("id") == hypothesis_id:
                h["status"] = status
                if finding:
                    h["finding"] = finding
                h["last_updated"] = datetime.now().strftime("%Y-%m-%d")
                break

    def add_open_question(self, question: str):
        """Add an open strategic question.

        Args:
            question: The question to track
        """
        questions = self.data.setdefault("open_questions", [])

        # Dedup
        if question in questions:
            return

        questions.append(question)

        if len(questions) > MAX_QUESTIONS:
            self.data["open_questions"] = questions[-MAX_QUESTIONS:]

    def remove_open_question(self, question: str):
        """Remove an answered/resolved question."""
        questions = self.data.get("open_questions", [])
        self.data["open_questions"] = [q for q in questions if q != question]

    def save(self):
        """Write to disk atomically."""
        self.data["last_updated"] = datetime.now().isoformat()

        CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = CONTEXT_PATH.with_suffix(".tmp")

        try:
            with open(tmp_path, "w") as f:
                json.dump(self.data, f, indent=2, default=str)
            os.rename(str(tmp_path), str(CONTEXT_PATH))
        except OSError as e:
            logger.error(f"Error saving strategic context: {e}")
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get_summary(self) -> str:
        """Summary for Claude session injection.

        Returns a concise text block for system prompt appending.
        """
        parts = []

        # Thesis momentum
        momentum = self.data.get("thesis_momentum", {})
        if momentum:
            trending = []
            for name, m in momentum.items():
                trend = m.get("trend", "unknown")
                history = m.get("conviction_history", [])
                latest = history[-1]["conviction"] if history else "?"
                if trend in ("rising", "declining"):
                    trending.append(f"{name}: {latest}% ({trend})")
            if trending:
                parts.append(f"Thesis trends: {', '.join(trending[:5])}")

        # Developing patterns
        patterns = self.data.get("developing_patterns", [])
        if patterns:
            active = [p for p in patterns if p.get("days_active", 0) >= 1]
            if active:
                pattern_texts = [f"{p['name']} ({p['days_active']}d)" for p in active[:3]]
                parts.append(f"Developing patterns: {', '.join(pattern_texts)}")

        # Signal source health
        trends = self.data.get("signal_source_trends", {})
        declining = [name for name, t in trends.items() if t.get("trend") == "declining"]
        if declining:
            parts.append(f"Declining signal sources: {', '.join(declining)}")

        # Upcoming catalysts (next 7 days)
        catalysts = self.data.get("upcoming_catalysts", [])
        from datetime import timedelta
        cutoff = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
        upcoming = [c for c in catalysts if c.get("date", "") <= cutoff and c.get("date", "") >= datetime.now().strftime("%Y-%m-%d")]
        if upcoming:
            cat_texts = [f"{c.get('date', '?')}: {c.get('event', c.get('description', '?'))}" for c in upcoming[:3]]
            parts.append(f"Upcoming catalysts: {', '.join(cat_texts)}")

        # Untested hypotheses
        hypotheses = self.data.get("research_hypotheses", [])
        untested = [h for h in hypotheses if h.get("status") == "untested"]
        if untested:
            parts.append(f"Untested hypotheses: {len(untested)}")

        # Blind spots (from theorist)
        blind_spots = self.data.get("blind_spots", [])
        if blind_spots:
            high = [bs for bs in blind_spots if isinstance(bs, dict) and bs.get("risk_level") == "high"]
            if high:
                bs_texts = [bs["description"][:50] for bs in high[:2]]
                parts.append(f"HIGH RISK blind spots: {', '.join(bs_texts)}")

        # Scenarios (from theorist)
        scenarios = self.data.get("scenarios", [])
        if scenarios:
            high_prob = [s for s in scenarios if isinstance(s, dict) and s.get("probability") == "high"]
            if high_prob:
                sc_texts = [s["name"] for s in high_prob[:2]]
                parts.append(f"High-probability scenarios: {', '.join(sc_texts)}")

        # Open questions
        questions = self.data.get("open_questions", [])
        if questions:
            parts.append(f"Open questions: {len(questions)}")

        return " || ".join(parts) if parts else "No strategic context yet."
