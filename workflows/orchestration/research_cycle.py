"""
Research Cycle Manager for On-Demand Quant Research.

Manages dual-track research cycles (Novel Patterns + Traditional Strategies)
with daily human review.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import json
import uuid

from .parallel_executor import (
    AgentTask,
    AgentType,
    DualTrackExecutor,
    ParallelAgentExecutor,
    create_full_research_tasks,
)
from .result_aggregator import ConsolidatedReport, ResearchResultAggregator


class CycleStatus(Enum):
    """Status of a research cycle."""
    CREATED = "created"
    RUNNING = "running"
    AWAITING_VALIDATION = "awaiting_validation"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchFocus(Enum):
    """Focus area for research."""
    SEMICONDUCTORS = "semiconductors"
    TECH = "tech"
    FINANCIALS = "financials"
    HEALTHCARE = "healthcare"
    ENERGY = "energy"
    ETFS = "etfs"
    MACRO = "macro"
    CUSTOM = "custom"


@dataclass
class CycleConfig:
    """Configuration for a research cycle."""
    focus: ResearchFocus
    sectors: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    max_parallel_agents: int = 3
    run_track1: bool = True  # Novel pattern discovery
    run_track2: bool = True  # Traditional strategy testing
    run_validation: bool = True  # Critic validation
    custom_prompt: str | None = None

    def __post_init__(self):
        # Set default sectors based on focus
        if not self.sectors:
            focus_sectors = {
                ResearchFocus.SEMICONDUCTORS: ["semiconductors"],
                ResearchFocus.TECH: ["tech", "semiconductors"],
                ResearchFocus.FINANCIALS: ["financials"],
                ResearchFocus.HEALTHCARE: ["healthcare"],
                ResearchFocus.ENERGY: ["energy"],
                ResearchFocus.ETFS: ["etfs"],
                ResearchFocus.MACRO: ["tech", "financials", "etfs"],
                ResearchFocus.CUSTOM: [],
            }
            self.sectors = focus_sectors.get(self.focus, [])

        # Set default strategies
        if not self.strategies:
            self.strategies = [
                "bollinger_reversal",
                "momentum",
                "mean_reversion",
                "rsi_reversal",
                "volatility_breakout",
            ]


@dataclass
class CycleReport:
    """Report from a completed research cycle."""
    cycle_id: str
    status: CycleStatus
    config: CycleConfig
    started_at: datetime
    completed_at: datetime | None
    consolidated: ConsolidatedReport | None
    human_decisions: dict | None
    error: str | None

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "status": self.status.value,
            "focus": self.config.focus.value,
            "sectors": self.config.sectors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "consolidated": self.consolidated.to_dict() if self.consolidated else None,
            "human_decisions": self.human_decisions,
            "error": self.error,
        }


class ResearchCycleManager:
    """
    Manage on-demand research cycles with daily review.

    Coordinates dual-track research:
    - Track 1: Novel pattern discovery (macro, news, regime)
    - Track 2: Traditional strategy testing

    Then aggregates results for human review.
    """

    def __init__(self, results_dir: str | None = None):
        self.results_dir = Path(results_dir or "/home/nock/quant_results/research_cycles")
        self.results_dir.mkdir(parents=True, exist_ok=True)

        self.dual_executor = DualTrackExecutor(max_parallel_per_track=2)
        self.aggregator = ResearchResultAggregator()

        self.current_cycle: CycleReport | None = None
        self.cycle_history: list[CycleReport] = []

        self._load_history()

    def _load_history(self) -> None:
        """Load cycle history from disk."""
        history_file = self.results_dir / "cycle_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    data = json.load(f)
                    # Just load IDs for now, full details available in individual files
                    self.cycle_history = []
            except Exception:
                pass

    def _save_cycle(self, cycle: CycleReport) -> None:
        """Save cycle to disk."""
        cycle_file = self.results_dir / f"{cycle.cycle_id}.json"
        with open(cycle_file, "w") as f:
            json.dump(cycle.to_dict(), f, indent=2, default=str)

    def start_cycle(
        self,
        focus: ResearchFocus | str,
        config: CycleConfig | None = None,
        custom_prompt: str | None = None
    ) -> str:
        """
        Start a new research cycle.

        Args:
            focus: Research focus area
            config: Optional configuration
            custom_prompt: Optional custom research prompt

        Returns:
            cycle_id: Unique identifier for this cycle
        """
        if isinstance(focus, str):
            try:
                focus = ResearchFocus(focus)
            except ValueError:
                focus = ResearchFocus.CUSTOM

        config = config or CycleConfig(focus=focus)
        if custom_prompt:
            config.custom_prompt = custom_prompt

        cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:4]}"

        self.current_cycle = CycleReport(
            cycle_id=cycle_id,
            status=CycleStatus.CREATED,
            config=config,
            started_at=datetime.now(),
            completed_at=None,
            consolidated=None,
            human_decisions=None,
            error=None,
        )

        self._save_cycle(self.current_cycle)
        return cycle_id

    def generate_cycle_prompts(self, cycle_id: str | None = None) -> dict:
        """
        Generate prompts for Task tool invocation.

        Returns dict with structure for spawning agents:
        {
            "cycle_id": str,
            "track1": [{"prompt": str, "description": str}, ...],
            "track2": [{"prompt": str, "description": str}, ...],
            "validation": [{"prompt": str, "description": str}, ...],
        }
        """
        cycle = self.current_cycle
        if not cycle:
            raise ValueError("No active cycle. Call start_cycle() first.")

        config = cycle.config
        prompts: dict[str, Any] = {"cycle_id": cycle.cycle_id}

        # Track 1: Novel Pattern Discovery
        if config.run_track1:
            track1_prompts = []

            # Macro research
            track1_prompts.append({
                "agent": "macro-research-agent",
                "prompt": f"""Research how macro factors are affecting {config.focus.value} sector.

Focus areas:
- Geopolitical events impacting {', '.join(config.sectors)}
- Economic indicators relevant to these sectors
- Interest rate sensitivity
- Currency impacts on earnings

Output structured findings as:
[FINDING] Description (confidence: 0.X)

Include actionable trading hypotheses where possible.""",
                "description": f"Macro research: {config.focus.value}",
            })

            # News analysis
            track1_prompts.append({
                "agent": "news-analyst-agent",
                "prompt": f"""Analyze recent news and events for {config.focus.value} sector.

Look for:
- Earnings surprises and guidance
- Supply chain developments
- Regulatory changes
- M&A activity
- Analyst rating changes

Timeframe: Last 7 days
Sectors: {', '.join(config.sectors)}

Output structured findings as:
[FINDING] Description (confidence: 0.X)""",
                "description": f"News analysis: {config.focus.value}",
            })

            # Regime detection
            track1_prompts.append({
                "agent": "regime-detector-agent",
                "prompt": """Classify current market regime.

Assess:
1. Volatility regime (VIX level, realized vs implied)
2. Sentiment regime (put/call ratio, fear/greed)
3. Correlation regime (risk-on vs risk-off)
4. Trend regime (trending vs range-bound)

Output format:
REGIME: [risk_on|risk_off|range_bound|trending|rotation]
CONFIDENCE: [0.0-1.0]
RECOMMENDED_STRATEGIES: [list]
AVOID_STRATEGIES: [list]""",
                "description": "Regime classification",
            })

            prompts["track1"] = track1_prompts

        # Track 2: Strategy Testing
        if config.run_track2:
            track2_prompts = []

            for sector in config.sectors:
                track2_prompts.append({
                    "agent": "research-worker-agent",
                    "prompt": f"""Test strategies on {sector} sector symbols.

Strategies to test: {', '.join(config.strategies)}

For each strategy/symbol combination:
1. Check if already tested in knowledge base
2. Run MCPT validation (p < 0.05 required)
3. Optimize PDT holding period (min 2 days)
4. Log results to session tracker

Output format (for each result):
| strategy | symbol | sharpe | p_value | hold_days |""",
                    "description": f"Research: {sector}",
                })

            prompts["track2"] = track2_prompts

        # Validation (after strategy testing)
        if config.run_validation:
            prompts["validation"] = [{
                "agent": "critic-agent",
                "prompt": """Validate the top 3 strategies from this research cycle.

Run full validation suite:
1. Lookahead bias detection
2. Overfitting check (OOS/IS ratio > 0.5)
3. Signal timing verification
4. Transaction cost sensitivity (0, 5, 10, 20 bps)
5. MCPT statistical significance

Verdict each as: APPROVE / NEEDS_REVIEW / REJECT""",
                "description": "Validate top strategies",
            }]

        return prompts

    def generate_orchestrator_prompt(self, cycle_id: str | None = None) -> str:
        """
        Generate a single prompt for the orchestrator agent to run the full cycle.

        This prompt can be used with a single Task tool call to run the complete
        research cycle using the orchestrator-agent.
        """
        cycle = self.current_cycle
        if not cycle:
            raise ValueError("No active cycle. Call start_cycle() first.")

        config = cycle.config

        return f"""Run a complete dual-track research cycle.

Cycle ID: {cycle.cycle_id}
Focus: {config.focus.value}
Sectors: {', '.join(config.sectors)}
Strategies: {', '.join(config.strategies)}

WORKFLOW:

1. TRACK 1 - Novel Pattern Discovery (run in parallel):
   - Spawn macro-research-agent for {config.focus.value} sector analysis
   - Spawn news-analyst-agent for recent news/events
   - Spawn regime-detector-agent for current regime classification

2. TRACK 2 - Strategy Testing (run in parallel):
   - For each sector {config.sectors}, spawn research-worker-agent
   - Test strategies: {', '.join(config.strategies)}
   - Ensure PDT compliance (min 2-day hold)

3. AGGREGATION:
   - Wait for all agents to complete
   - Collect and deduplicate findings
   - Identify cross-track patterns

4. VALIDATION:
   - Use critic-agent to validate top 3 strategies

5. GENERATE DAILY REVIEW:
   - Compile findings for human review
   - List promotion candidates
   - Suggest next priorities

OUTPUT FORMAT:
=== ORCHESTRATION SUMMARY ===
Cycle ID: {cycle.cycle_id}
Status: [completed/partial]

AGENTS EXECUTED:
1. [Agent] - [Status] - [Duration]

NOVEL PATTERNS:
[List findings from Track 1]

STRATEGY RESULTS:
[Table of results from Track 2]

REGIME ASSESSMENT:
[Current regime and recommendations]

PROMOTION CANDIDATES:
[Strategies ready for budget_pool]

NEXT PRIORITIES:
[Suggested research leads]
"""

    def run_dual_track(self) -> CycleReport:
        """
        Run both tracks of research.

        NOTE: This method generates the structure for agent execution.
        Actual execution happens via Task tool in Claude Code.
        """
        if not self.current_cycle:
            raise ValueError("No active cycle")

        self.current_cycle.status = CycleStatus.RUNNING
        self._save_cycle(self.current_cycle)

        # Generate tasks for both tracks
        config = self.current_cycle.config
        prompts = self.dual_executor.generate_dual_track_prompts(
            focus=config.focus.value,
            sectors=config.sectors,
            strategies=config.strategies,
        )

        # The actual parallel execution is done via Task tool
        # This method returns the current state
        return self.current_cycle

    def mark_awaiting_review(self, consolidated_report: ConsolidatedReport) -> None:
        """Mark cycle as awaiting human review."""
        if not self.current_cycle:
            return

        self.current_cycle.status = CycleStatus.AWAITING_REVIEW
        self.current_cycle.consolidated = consolidated_report
        self._save_cycle(self.current_cycle)

    def record_human_decisions(self, decisions: dict) -> None:
        """
        Record human decisions from daily review.

        Expected decisions format:
        {
            "promotions": [{"strategy": str, "symbol": str, "approved": bool}],
            "priorities_accepted": bool,
            "custom_priorities": [str],
            "notes": str,
        }
        """
        if not self.current_cycle:
            return

        self.current_cycle.human_decisions = decisions
        self.current_cycle.status = CycleStatus.COMPLETED
        self.current_cycle.completed_at = datetime.now()

        self.cycle_history.append(self.current_cycle)
        self._save_cycle(self.current_cycle)

        self.current_cycle = None

    def generate_daily_review(self) -> str:
        """
        Generate daily review markdown for human approval.

        Returns markdown string formatted for human review.
        """
        if not self.current_cycle or not self.current_cycle.consolidated:
            return "No cycle results available for review."

        report = self.current_cycle.consolidated
        return report.to_markdown()

    def get_cycle_status(self, cycle_id: str | None = None) -> dict:
        """Get status of a cycle."""
        if cycle_id:
            # Load from file
            cycle_file = self.results_dir / f"{cycle_id}.json"
            if cycle_file.exists():
                with open(cycle_file) as f:
                    return json.load(f)
            return {"error": "Cycle not found"}

        if self.current_cycle:
            return self.current_cycle.to_dict()

        return {"status": "no_active_cycle"}


# Convenience functions for quick cycle creation
def quick_semiconductor_cycle() -> ResearchCycleManager:
    """Create a quick semiconductor research cycle."""
    manager = ResearchCycleManager()
    manager.start_cycle(ResearchFocus.SEMICONDUCTORS)
    return manager


def quick_tech_cycle() -> ResearchCycleManager:
    """Create a quick tech research cycle."""
    manager = ResearchCycleManager()
    manager.start_cycle(ResearchFocus.TECH)
    return manager


def full_research_cycle(sectors: list[str] | None = None) -> ResearchCycleManager:
    """Create a full research cycle across multiple sectors."""
    manager = ResearchCycleManager()
    config = CycleConfig(
        focus=ResearchFocus.CUSTOM,
        sectors=sectors or ["tech", "semiconductors", "financials", "etfs"],
        max_parallel_agents=4,
    )
    manager.start_cycle(ResearchFocus.CUSTOM, config=config)
    return manager
