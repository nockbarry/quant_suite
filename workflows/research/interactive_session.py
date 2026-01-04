"""
Interactive Research Session Protocol

Provides structured entry points for Claude Code research sessions:
- Session start briefings
- Experiment execution
- Progress tracking
- Knowledge queries

Usage:
    # At session start
    briefing = await start_research_session()
    print(briefing.summary)

    # Run experiments
    result = await run_experiment('momentum_20d', 'AAPL')

    # Check what's tested
    coverage = what_is_tested()
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from workflows.research.knowledge_base import KnowledgeBase
from workflows.research.research_dashboard import ResearchDashboard
from workflows.research.session_context import SessionContext


@dataclass
class SessionBriefing:
    """Comprehensive briefing for starting a research session."""

    # Stats
    total_experiments: int
    total_successes: int
    total_failures: int

    # What's working
    significant_strategies: list[dict]
    patterns_discovered: list[dict]

    # What to avoid
    failed_strategies_summary: dict
    difficult_symbols: list[str]

    # What to try next
    suggested_experiments: list[dict]
    untested_combinations: list[tuple[str, str]]

    # Session continuity
    last_session: dict | None
    last_session_summary: str

    # Briefing text
    briefing_text: str

    @property
    def summary(self) -> str:
        """Short summary for quick reference."""
        return f"""
Research Session Ready
======================
Experiments: {self.total_experiments} run ({self.total_successes} significant)
Top strategy: {self.significant_strategies[0]['strategy'] if self.significant_strategies else 'None yet'}
Gaps: {len(self.untested_combinations)} untested combinations
Last session: {self.last_session_summary}
"""


async def start_research_session() -> SessionBriefing:
    """
    Called at start of Claude Code research session.

    Gathers all context needed to continue research effectively.

    Returns:
        SessionBriefing with comprehensive state
    """
    kb = KnowledgeBase()
    dashboard = ResearchDashboard()
    context = SessionContext()

    # Get dashboard status
    status = dashboard.get_status()

    # Get failure summary
    failure_summary = kb.summarize_failures()

    # Get patterns
    patterns = [
        {"name": p.name, "confidence": p.confidence, "symbols": p.symbols}
        for p in kb.get_patterns(min_confidence=0.5)
    ]

    # Get promising variations
    variations = kb.get_promising_variations(10)

    # Get untested combinations
    from workflows.research.research_dashboard import KNOWN_STRATEGIES, DEFAULT_SYMBOLS
    untested = kb.get_untested_combinations(KNOWN_STRATEGIES, DEFAULT_SYMBOLS)[:20]

    # Session continuity
    last_session = context.load_last_session()
    if last_session:
        last_summary = f"{last_session.get('focus_strategy', 'Various')} - {last_session.get('saved_at', 'Unknown')[:10]}"
    else:
        last_summary = "New session"

    # Full briefing text
    briefing_text = context.get_briefing()

    return SessionBriefing(
        total_experiments=status["total_experiments"],
        total_successes=status["total_successes"],
        total_failures=status["total_failures"],
        significant_strategies=status["significant_strategies"],
        patterns_discovered=patterns,
        failed_strategies_summary=failure_summary,
        difficult_symbols=failure_summary.get("difficult_symbols", []),
        suggested_experiments=variations,
        untested_combinations=untested,
        last_session=last_session,
        last_session_summary=last_summary,
        briefing_text=briefing_text,
    )


def what_works() -> list[dict]:
    """
    Show strategies that have demonstrated statistical significance.

    Returns list of successful strategy-symbol combinations.
    """
    kb = KnowledgeBase()
    return [
        {
            "strategy": s.strategy_name,
            "symbol": s.symbol,
            "sharpe": s.val_sharpe,
            "p_value": s.p_value,
            "params": s.params,
        }
        for s in kb.get_successful_strategies(min_sharpe=0.5)
    ]


def what_failed() -> dict:
    """
    Show what strategies and symbols have consistently failed.

    Returns summary to help avoid wasting time.
    """
    kb = KnowledgeBase()
    return kb.summarize_failures()


def what_is_tested() -> dict:
    """
    Show coverage matrix - what's been tested.

    Returns detailed breakdown of tested vs untested.
    """
    dashboard = ResearchDashboard()
    status = dashboard.get_status()

    return {
        "coverage_pct": status["coverage_pct"],
        "tested_pairs": status["coverage_details"]["tested_pairs"],
        "total_possible": status["coverage_details"]["total_possible"],
        "strategies_tested": status["coverage_details"]["strategies_tested"],
        "symbols_covered": status["coverage_details"]["symbols_covered"],
        "gaps": status["gaps"][:20],
    }


def should_run(strategy: str, symbol: str, params: dict | None = None) -> dict:
    """
    Check if an experiment should be run.

    Returns recommendation: 'skip', 'run', or 'run_with_variation'.
    """
    kb = KnowledgeBase()
    return kb.check_before_experiment(strategy, symbol, params)


def get_next_experiments(n: int = 5) -> list[dict]:
    """
    Get suggested next experiments to run.

    Returns high-priority experiments based on what's worked.
    """
    kb = KnowledgeBase()
    return kb.get_promising_variations(n)


def save_session(
    focus_strategy: str | None = None,
    focus_symbols: list[str] | None = None,
    notes: str | None = None,
    next_steps: list[str] | None = None,
) -> None:
    """
    Save current session state for resuming later.
    """
    context = SessionContext()
    state = context.load_last_session() or {}

    if focus_strategy:
        state["focus_strategy"] = focus_strategy
    if focus_symbols:
        state["focus_symbols"] = focus_symbols
    if notes:
        state["notes"] = notes
    if next_steps:
        state["next_steps"] = next_steps

    context.save_session_state(state)


def get_strategy_analysis(strategy_name: str) -> dict:
    """
    Get detailed analysis of a specific strategy.
    """
    dashboard = ResearchDashboard()
    return dashboard.get_strategy_performance(strategy_name)


def get_symbol_analysis(symbol: str) -> dict:
    """
    Get detailed analysis of a specific symbol.
    """
    dashboard = ResearchDashboard()
    return dashboard.get_symbol_performance(symbol)


# Quick commands for interactive use

def status() -> None:
    """Print quick status to console."""
    dashboard = ResearchDashboard()
    s = dashboard.get_status()

    print(f"""
Research Status
===============
Experiments: {s['total_experiments']} total
Significant: {s['total_successes']} strategies work
Coverage:    {s['coverage_pct']:.1f}%
Gaps:        {s['total_gaps']} untested combinations
""")

    if s['significant_strategies']:
        print("Top 3 Strategies:")
        for i, st in enumerate(s['significant_strategies'][:3], 1):
            print(f"  {i}. {st['strategy']} on {st['symbol']} (Sharpe={st['val_sharpe']})")


def help_research() -> None:
    """Print available research commands."""
    print("""
Interactive Research Commands
=============================

Session Management:
  start_research_session()  - Get full briefing at session start
  save_session(...)         - Save current state for resuming

What to Know:
  what_works()              - Show successful strategies
  what_failed()             - Show what to avoid
  what_is_tested()          - Show coverage matrix

Planning:
  should_run(strat, sym)    - Check if experiment should be run
  get_next_experiments(n)   - Get suggested experiments

Analysis:
  get_strategy_analysis(s)  - Analyze a strategy
  get_symbol_analysis(s)    - Analyze a symbol
  status()                  - Quick status print
""")


if __name__ == "__main__":
    import asyncio

    async def main():
        print("Starting research session...")
        briefing = await start_research_session()
        print(briefing.summary)
        print()
        print("Full briefing:")
        print(briefing.briefing_text)

    asyncio.run(main())
