"""
Session Context - Cross-Session Continuity for Claude Code

Maintains research context across Claude Code sessions:
- Saves current research direction and hypotheses in progress
- Loads state from last session to resume work
- Generates briefings for session start

Usage:
    context = SessionContext()

    # At session end
    context.save_session_state({
        'focus_strategy': 'momentum_20d',
        'hypotheses_in_progress': [...],
        'notes': 'Testing momentum on tech stocks',
    })

    # At session start
    last_session = context.load_last_session()
    briefing = context.get_briefing()
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))

from workflows.research.knowledge_base import KnowledgeBase
from workflows.research.research_dashboard import ResearchDashboard


class SessionContext:
    """
    Persists context for Claude Code research sessions.

    Enables seamless continuation of research across multiple sessions
    by tracking what was being worked on and what to do next.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or _RESULTS_DIR / "sessions"
        self.path.mkdir(parents=True, exist_ok=True)

        self._context_file = self.path / "claude_session_context.json"
        self._history_file = self.path / "session_history.json"

        self.kb = KnowledgeBase()
        self.dashboard = ResearchDashboard()

    def save_session_state(self, state: dict) -> None:
        """
        Save current research direction and hypotheses in progress.

        Args:
            state: Dictionary containing:
                - focus_strategy: Current strategy being tested
                - focus_symbols: Symbols being tested
                - hypotheses_in_progress: Hypotheses not yet completed
                - experiments_run: List of experiments run this session
                - notes: Free-form notes about the research
                - next_steps: Planned next actions
        """
        # Add metadata
        state["session_id"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        state["saved_at"] = datetime.now().isoformat()

        # Save current state
        self._context_file.write_text(json.dumps(state, indent=2))

        # Append to history
        history = self._load_history()
        history.append({
            "session_id": state["session_id"],
            "saved_at": state["saved_at"],
            "summary": self._summarize_state(state),
        })
        # Keep last 50 sessions
        history = history[-50:]
        self._history_file.write_text(json.dumps(history, indent=2))

    def _summarize_state(self, state: dict) -> str:
        """Create brief summary of session state."""
        parts = []
        if state.get("focus_strategy"):
            parts.append(f"Strategy: {state['focus_strategy']}")
        if state.get("focus_symbols"):
            symbols = state["focus_symbols"][:3]
            parts.append(f"Symbols: {', '.join(symbols)}")
        if state.get("experiments_run"):
            parts.append(f"Experiments: {len(state['experiments_run'])}")
        return " | ".join(parts) if parts else "No details"

    def _load_history(self) -> list:
        """Load session history."""
        if self._history_file.exists():
            return json.loads(self._history_file.read_text())
        return []

    def load_last_session(self) -> dict | None:
        """
        Load the last saved session state.

        Returns:
            Dictionary with last session's state, or None if no saved session.
        """
        if not self._context_file.exists():
            return None

        try:
            return json.loads(self._context_file.read_text())
        except json.JSONDecodeError:
            return None

    def get_briefing(self) -> str:
        """
        Generate a briefing for Claude at session start.

        This provides comprehensive context including:
        - What we've learned overall
        - What's working (successful strategies)
        - What to try next
        - What to avoid
        - What was being worked on last session
        """
        lines = [
            "=" * 60,
            "RESEARCH SESSION BRIEFING",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]

        # Last session context
        last_session = self.load_last_session()
        if last_session:
            lines.extend([
                "## Previous Session",
                f"- Last active: {last_session.get('saved_at', 'Unknown')}",
            ])
            if last_session.get("focus_strategy"):
                lines.append(f"- Focus: {last_session['focus_strategy']}")
            if last_session.get("hypotheses_in_progress"):
                lines.append(f"- In progress: {len(last_session['hypotheses_in_progress'])} hypotheses")
            if last_session.get("notes"):
                lines.append(f"- Notes: {last_session['notes']}")
            if last_session.get("next_steps"):
                lines.append("- Planned next:")
                for step in last_session["next_steps"][:3]:
                    lines.append(f"  * {step}")
            lines.append("")

        # Knowledge base stats
        kb_summary = self.kb.summary()
        lines.extend([
            "## Research Progress",
            f"- Total tested: {kb_summary['tested_hypotheses']} hypotheses",
            f"- Successful: {kb_summary['total_successes']}",
            f"- Failed: {kb_summary['total_failures']}",
            f"- Patterns found: {kb_summary['total_patterns']}",
            "",
        ])

        # What's working
        winning = self.kb.get_successful_strategies(min_sharpe=1.0)
        if winning:
            lines.extend([
                "## What's Working (Sharpe > 1.0)",
            ])
            for s in winning[:5]:
                lines.append(
                    f"- {s.strategy_name} on {s.symbol}: "
                    f"Sharpe={s.val_sharpe:.2f}, p={s.p_value:.3f}"
                )
            lines.append("")

        # What to avoid
        failure_summary = self.kb.summarize_failures()
        if failure_summary["avoid_strategies"]:
            lines.extend([
                "## Strategies to Avoid (consistently failing)",
                f"- {', '.join(failure_summary['avoid_strategies'][:5])}",
                "",
            ])

        if failure_summary["difficult_symbols"]:
            lines.extend([
                "## Difficult Symbols (many strategies fail)",
                f"- {', '.join(failure_summary['difficult_symbols'][:5])}",
                "",
            ])

        # What to try next
        variations = self.kb.get_promising_variations(5)
        if variations:
            lines.extend([
                "## Suggested Next Experiments",
            ])
            for v in variations:
                lines.append(
                    f"- {v['strategy']} on {v['symbol']}: {v['reason']}"
                )
            lines.append("")

        # Patterns discovered
        patterns = self.kb.get_patterns(min_confidence=0.6)
        if patterns:
            lines.extend([
                "## Discovered Patterns",
            ])
            for p in patterns[:3]:
                lines.append(
                    f"- {p.name}: {p.description} (confidence: {p.confidence:.0%})"
                )
            lines.append("")

        # Recent insights
        insights = self.kb.get_insights(min_confidence=0.5)
        if insights:
            lines.extend([
                "## Recent High-Confidence Insights",
            ])
            for i in insights[:5]:
                lines.append(f"- [{i.category}] {i.content}")
            lines.append("")

        lines.extend([
            "=" * 60,
            "Ready to continue research",
            "=" * 60,
        ])

        return "\n".join(lines)

    def record_experiment(
        self,
        strategy: str,
        symbol: str,
        params: dict,
        result: str,
        sharpe: float | None = None,
    ) -> None:
        """
        Record an experiment run during this session.

        This updates the current session context with the experiment.
        """
        state = self.load_last_session() or {}

        if "experiments_run" not in state:
            state["experiments_run"] = []

        state["experiments_run"].append({
            "strategy": strategy,
            "symbol": symbol,
            "params": params,
            "result": result,
            "sharpe": sharpe,
            "timestamp": datetime.now().isoformat(),
        })

        self.save_session_state(state)

    def set_focus(self, strategy: str | None = None, symbols: list[str] | None = None) -> None:
        """
        Set current research focus.

        Args:
            strategy: Strategy to focus on
            symbols: Symbols to focus on
        """
        state = self.load_last_session() or {}

        if strategy:
            state["focus_strategy"] = strategy
        if symbols:
            state["focus_symbols"] = symbols

        self.save_session_state(state)

    def add_note(self, note: str) -> None:
        """Add a note to the current session."""
        state = self.load_last_session() or {}

        if "notes" not in state:
            state["notes"] = ""

        state["notes"] += f"\n[{datetime.now().strftime('%H:%M')}] {note}"
        self.save_session_state(state)

    def set_next_steps(self, steps: list[str]) -> None:
        """Set planned next steps."""
        state = self.load_last_session() or {}
        state["next_steps"] = steps
        self.save_session_state(state)

    def get_session_history(self, n: int = 10) -> list[dict]:
        """Get recent session history."""
        history = self._load_history()
        return history[-n:]

    def clear_session(self) -> None:
        """Clear current session context (start fresh)."""
        if self._context_file.exists():
            self._context_file.unlink()


def get_session_briefing() -> str:
    """Quick function to get session briefing."""
    context = SessionContext()
    return context.get_briefing()


def resume_research() -> dict:
    """
    Load last session and return context for resuming.

    Returns dictionary with:
    - last_session: Previous session state
    - briefing: Full briefing text
    - next_steps: Suggested next actions
    """
    context = SessionContext()

    last_session = context.load_last_session()
    briefing = context.get_briefing()

    # Get suggested next steps
    variations = context.kb.get_promising_variations(5)
    next_steps = [
        f"{v['strategy']} on {v['symbol']}"
        for v in variations
    ]

    return {
        "last_session": last_session,
        "briefing": briefing,
        "next_steps": next_steps,
    }


if __name__ == "__main__":
    context = SessionContext()

    # Display briefing
    print(context.get_briefing())

    # Show session history
    print("\n\nSession History:")
    for session in context.get_session_history(5):
        print(f"  {session['session_id']}: {session['summary']}")
