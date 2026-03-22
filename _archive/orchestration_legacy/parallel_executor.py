"""
Parallel Agent Executor for Multi-Agent Research Workflows.

Manages spawning and tracking multiple Claude Code subagents for parallel research.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json
import uuid
from pathlib import Path


class AgentType(Enum):
    """Available agent types for orchestration."""
    RESEARCH_WORKER = "research-worker"
    MACRO_RESEARCH = "macro-research"
    NEWS_ANALYST = "news-analyst"
    REGIME_DETECTOR = "regime-detector"
    CRITIC = "critic"
    BRAINSTORM = "brainstorm"
    MONITOR = "monitor"
    FEATURE = "feature"
    PROMOTER = "promoter"


class TaskStatus(Enum):
    """Status of an agent task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class AgentTask:
    """Definition of an agent task to execute."""
    agent_type: AgentType
    prompt: str
    description: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    priority: int = 1
    dependencies: list[str] = field(default_factory=list)
    timeout_seconds: int = 300
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AgentResult:
    """Result from an agent execution."""
    task_id: str
    agent_type: AgentType
    status: TaskStatus
    output: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.COMPLETED

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "agent_type": self.agent_type.value,
            "status": self.status.value,
            "output": self.output[:500] + "..." if len(self.output) > 500 else self.output,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "success": self.success,
        }


class ParallelAgentExecutor:
    """
    Execute multiple Claude Code subagents in parallel with dependency tracking.

    This class provides the structure for orchestrating parallel agent execution.
    Actual spawning happens via the Task tool in Claude Code - this class
    generates the prompts and tracks results.
    """

    def __init__(self, max_parallel: int = 3, results_dir: str | None = None):
        self.max_parallel = max_parallel
        self.results_dir = Path(results_dir or "/home/nock/quant_results/agent_runs")
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.pending_tasks: list[AgentTask] = []
        self.running_tasks: dict[str, AgentTask] = {}
        self.completed_results: list[AgentResult] = []

    def add_task(self, task: AgentTask) -> str:
        """Add a task to the pending queue. Returns task_id."""
        self.pending_tasks.append(task)
        return task.task_id

    def add_tasks(self, tasks: list[AgentTask]) -> list[str]:
        """Add multiple tasks to the queue."""
        return [self.add_task(t) for t in tasks]

    def get_ready_tasks(self) -> list[AgentTask]:
        """Get tasks ready to run (dependencies satisfied, under parallel limit)."""
        completed_ids = {r.task_id for r in self.completed_results}
        running_count = len(self.running_tasks)
        available_slots = self.max_parallel - running_count

        ready = []
        for task in self.pending_tasks:
            if available_slots <= 0:
                break
            # Check if all dependencies are completed
            deps_satisfied = all(dep in completed_ids for dep in task.dependencies)
            if deps_satisfied:
                ready.append(task)
                available_slots -= 1

        return ready

    def mark_running(self, task_id: str) -> None:
        """Mark a task as running."""
        for i, task in enumerate(self.pending_tasks):
            if task.task_id == task_id:
                self.running_tasks[task_id] = self.pending_tasks.pop(i)
                break

    def mark_completed(self, result: AgentResult) -> None:
        """Mark a task as completed with its result."""
        if result.task_id in self.running_tasks:
            del self.running_tasks[result.task_id]
        self.completed_results.append(result)
        self._save_result(result)

    def _save_result(self, result: AgentResult) -> None:
        """Save result to file."""
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{result.task_id}.json"
        filepath = self.results_dir / filename
        with open(filepath, "w") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

    def generate_parallel_prompts(self, tasks: list[AgentTask]) -> list[dict]:
        """
        Generate prompts for parallel Task tool invocations.

        Returns list of dicts with 'agent_type', 'prompt', 'description' for each task.
        These should be spawned via Task tool with subagent_type="general-purpose".
        """
        return [
            {
                "task_id": task.task_id,
                "agent_type": task.agent_type.value,
                "prompt": self._build_agent_prompt(task),
                "description": task.description,
            }
            for task in tasks
        ]

    def _build_agent_prompt(self, task: AgentTask) -> str:
        """Build the full prompt for an agent task."""
        agent_prompts = {
            AgentType.RESEARCH_WORKER: self._research_worker_prompt,
            AgentType.MACRO_RESEARCH: self._macro_research_prompt,
            AgentType.NEWS_ANALYST: self._news_analyst_prompt,
            AgentType.REGIME_DETECTOR: self._regime_detector_prompt,
            AgentType.CRITIC: self._critic_prompt,
            AgentType.BRAINSTORM: self._brainstorm_prompt,
        }

        builder = agent_prompts.get(task.agent_type)
        if builder:
            return builder(task)
        return task.prompt

    def _research_worker_prompt(self, task: AgentTask) -> str:
        """Build research worker prompt from task metadata."""
        symbols = task.metadata.get("symbols", [])
        strategies = task.metadata.get("strategies", [])
        return f"""Use the research-worker-agent to test strategies on the specified symbols.

Focus: {task.metadata.get('focus', 'general research')}
Symbols: {', '.join(symbols) if symbols else 'Choose appropriate symbols'}
Strategies: {', '.join(strategies) if strategies else 'All available strategies'}

Instructions:
1. Check knowledge base for already-tested combinations
2. Run validation with MCPT for untested combinations
3. Log results to session tracker
4. Return structured summary of findings

{task.prompt}
"""

    def _macro_research_prompt(self, task: AgentTask) -> str:
        """Build macro research prompt."""
        focus = task.metadata.get("macro_focus", "general")
        return f"""Use the macro-research-agent to explore macro factor relationships.

Focus Area: {focus}
Sectors: {task.metadata.get('sectors', 'all')}

Research Questions:
{task.prompt}

Output format: Structured hypotheses about macro → market relationships
"""

    def _news_analyst_prompt(self, task: AgentTask) -> str:
        """Build news analyst prompt."""
        return f"""Use the news-analyst-agent to analyze current events.

Focus: {task.metadata.get('event_focus', 'general news')}
Timeframe: {task.metadata.get('timeframe', 'last 7 days')}

Analysis requested:
{task.prompt}

Output format: Event-driven trading hypotheses with evidence
"""

    def _regime_detector_prompt(self, task: AgentTask) -> str:
        """Build regime detector prompt."""
        return f"""Use the regime-detector-agent to classify current market regime.

{task.prompt}

Assess:
1. Volatility regime (VIX, realized vol)
2. Sentiment regime (fear/greed indicators)
3. Correlation regime (risk-on/risk-off)
4. Trend regime (trending vs range-bound)

Output format: Current regime classification with strategy recommendations
"""

    def _critic_prompt(self, task: AgentTask) -> str:
        """Build critic validation prompt."""
        strategy = task.metadata.get("strategy", "unknown")
        symbol = task.metadata.get("symbol", "unknown")
        return f"""Use the critic-agent to validate {strategy} on {symbol}.

{task.prompt}

Run full validation suite:
1. Lookahead bias detection
2. Overfitting check (OOS/IS ratio)
3. Signal timing verification
4. Transaction cost sensitivity
5. MCPT statistical significance

Verdict: APPROVE / NEEDS_REVIEW / REJECT
"""

    def _brainstorm_prompt(self, task: AgentTask) -> str:
        """Build brainstorm prompt."""
        domain = task.metadata.get("domain", "general")
        return f"""Use the brainstorm-agent to generate ideas.

Focus Domain: {domain}

{task.prompt}

Output:
1. New feature ideas with rationale
2. Strategy variations to test
3. Gap analysis for under-explored areas
"""

    def get_execution_summary(self) -> dict:
        """Get summary of execution state."""
        return {
            "pending": len(self.pending_tasks),
            "running": len(self.running_tasks),
            "completed": len(self.completed_results),
            "successful": sum(1 for r in self.completed_results if r.success),
            "failed": sum(1 for r in self.completed_results if not r.success),
            "tasks": {
                "pending": [t.task_id for t in self.pending_tasks],
                "running": list(self.running_tasks.keys()),
                "completed": [r.task_id for r in self.completed_results],
            }
        }


class DualTrackExecutor:
    """
    Execute dual-track research: Novel Pattern + Traditional Strategy.

    Track 1: Macro research, news analysis, regime detection
    Track 2: Traditional strategy testing across sectors
    """

    def __init__(self, max_parallel_per_track: int = 2):
        self.track1_executor = ParallelAgentExecutor(
            max_parallel=max_parallel_per_track,
            results_dir="/home/nock/quant_results/agent_runs/track1_novel"
        )
        self.track2_executor = ParallelAgentExecutor(
            max_parallel=max_parallel_per_track,
            results_dir="/home/nock/quant_results/agent_runs/track2_strategy"
        )

    def create_track1_tasks(self, focus: str, config: dict) -> list[AgentTask]:
        """Create Track 1 (Novel Pattern) tasks."""
        tasks = []

        # Macro research task
        tasks.append(AgentTask(
            agent_type=AgentType.MACRO_RESEARCH,
            prompt=f"Research macro factors affecting {focus}",
            description=f"Macro research: {focus}",
            metadata={
                "macro_focus": focus,
                "sectors": config.get("sectors", []),
            }
        ))

        # News analysis task
        tasks.append(AgentTask(
            agent_type=AgentType.NEWS_ANALYST,
            prompt=f"Analyze recent news for {focus} sector",
            description=f"News analysis: {focus}",
            metadata={
                "event_focus": focus,
                "timeframe": config.get("news_timeframe", "7d"),
            }
        ))

        # Regime detection task
        tasks.append(AgentTask(
            agent_type=AgentType.REGIME_DETECTOR,
            prompt="Classify current market regime and recommend strategies",
            description="Regime detection",
            metadata={}
        ))

        return tasks

    def create_track2_tasks(self, sectors: list[str], strategies: list[str]) -> list[AgentTask]:
        """Create Track 2 (Strategy Testing) tasks - one per sector."""
        tasks = []

        # Symbol mappings per sector
        sector_symbols = {
            "tech": ["AAPL", "MSFT", "GOOGL", "META"],
            "semiconductors": ["NVDA", "AMD", "QCOM", "MU", "MRVL", "AVGO"],
            "financials": ["JPM", "GS", "V", "MA", "BAC"],
            "etfs": ["SPY", "QQQ", "IWM", "DIA", "XLK"],
            "healthcare": ["JNJ", "UNH", "PFE", "MRK"],
            "energy": ["XOM", "CVX", "COP", "SLB"],
        }

        for sector in sectors:
            symbols = sector_symbols.get(sector, [])
            tasks.append(AgentTask(
                agent_type=AgentType.RESEARCH_WORKER,
                prompt=f"Test all strategies on {sector} sector symbols",
                description=f"Research: {sector}",
                metadata={
                    "focus": sector,
                    "symbols": symbols,
                    "strategies": strategies,
                }
            ))

        return tasks

    def generate_dual_track_prompts(
        self,
        focus: str,
        sectors: list[str],
        strategies: list[str],
        config: dict | None = None
    ) -> dict[str, list[dict]]:
        """
        Generate prompts for both tracks.

        Returns dict with 'track1' and 'track2' keys, each containing
        list of task prompts ready for Task tool invocation.
        """
        config = config or {}

        track1_tasks = self.create_track1_tasks(focus, config)
        track2_tasks = self.create_track2_tasks(sectors, strategies)

        self.track1_executor.add_tasks(track1_tasks)
        self.track2_executor.add_tasks(track2_tasks)

        return {
            "track1": self.track1_executor.generate_parallel_prompts(track1_tasks),
            "track2": self.track2_executor.generate_parallel_prompts(track2_tasks),
        }

    def get_combined_summary(self) -> dict:
        """Get combined summary from both tracks."""
        return {
            "track1_novel_patterns": self.track1_executor.get_execution_summary(),
            "track2_strategy_testing": self.track2_executor.get_execution_summary(),
            "total_pending": (
                len(self.track1_executor.pending_tasks) +
                len(self.track2_executor.pending_tasks)
            ),
            "total_completed": (
                len(self.track1_executor.completed_results) +
                len(self.track2_executor.completed_results)
            ),
        }


# Factory functions for creating common task sets
def create_semiconductor_research_tasks() -> list[AgentTask]:
    """Create tasks for semiconductor sector research."""
    executor = DualTrackExecutor()

    # Track 1: Novel patterns
    track1 = executor.create_track1_tasks(
        focus="semiconductors",
        config={"sectors": ["semiconductors", "tech"]}
    )

    # Track 2: Strategy testing
    track2 = executor.create_track2_tasks(
        sectors=["semiconductors"],
        strategies=["bollinger_reversal", "momentum", "mean_reversion", "volatility_breakout"]
    )

    return track1 + track2


def create_full_research_tasks(
    sectors: list[str] | None = None,
    strategies: list[str] | None = None
) -> list[AgentTask]:
    """Create comprehensive research tasks."""
    executor = DualTrackExecutor()

    sectors = sectors or ["tech", "semiconductors", "financials", "etfs"]
    strategies = strategies or ["bollinger_reversal", "momentum", "mean_reversion", "rsi_reversal"]

    # Track 1: Novel patterns for primary sector
    track1 = executor.create_track1_tasks(
        focus=sectors[0],
        config={"sectors": sectors}
    )

    # Track 2: Strategy testing across all sectors
    track2 = executor.create_track2_tasks(sectors, strategies)

    # Add brainstorm task
    brainstorm = AgentTask(
        agent_type=AgentType.BRAINSTORM,
        prompt="Generate new feature and strategy ideas based on recent research",
        description="Brainstorm session",
        metadata={"domain": "general"}
    )

    return track1 + track2 + [brainstorm]
