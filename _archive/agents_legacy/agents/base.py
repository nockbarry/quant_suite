"""
Base agent configuration and result types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentStatus(Enum):
    """Agent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentConfig:
    """Configuration for a quant agent."""

    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    working_dirs: list[str] = field(default_factory=list)
    timeout_minutes: int = 30

    # Context information
    key_files: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)

    def get_full_prompt(self, task: str) -> str:
        """Generate full prompt with context for the agent."""
        context = f"""
# Agent: {self.name}
{self.description}

## Available Skills
{', '.join(self.skills) if self.skills else 'None'}

## Key Files
{self._format_key_files()}

## Working Directories
{chr(10).join(f'- {d}' for d in self.working_dirs)}

## CRITICAL: Execution Guidelines
- Always use `python3` (not `python`)
- Use `timeout` with bash commands: `timeout 120 python3 script.py`
- If a command fails or times out, do NOT retry more than twice
- Move on and note failures in your summary report
- Complete your task even if some commands fail

## Task
{task}

{self.system_prompt}
"""
        return context.strip()

    def _format_key_files(self) -> str:
        """Format key files for prompt."""
        if not self.key_files:
            return "None"
        return "\n".join(f"- {name}: `{path}`" for name, path in self.key_files.items())


@dataclass
class AgentResult:
    """Result from an agent execution."""

    agent_name: str
    task: str
    status: AgentStatus
    started_at: datetime
    completed_at: datetime | None = None

    # Outputs
    summary: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)  # File paths created
    metrics: dict[str, Any] = field(default_factory=dict)

    # Errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Follow-up
    next_steps: list[str] = field(default_factory=list)
    recommended_agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_name": self.agent_name,
            "task": self.task,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "summary": self.summary,
            "findings": self.findings,
            "artifacts": self.artifacts,
            "metrics": self.metrics,
            "errors": self.errors,
            "warnings": self.warnings,
            "next_steps": self.next_steps,
            "recommended_agents": self.recommended_agents,
        }


# Common paths used by all agents
QUANT_PATHS = {
    "results": "/home/nock/quant_results",
    "research": "/home/nock/quant_results/comprehensive_research",
    "validation": "/home/nock/quant_results/validation_reports",
    "critic": "/home/nock/quant_results/critic_reports",
    "promotions": "/home/nock/quant_results/promotions",
    "tracker": "/home/nock/quant_results/research_tracker",
    "strategies": "/home/nock/projects/quant_suite/config/strategies",
    "scripts": "/home/nock/projects/quant_suite/scripts",
    "skills": "/home/nock/projects/quant_suite/.claude/skills",
}

# Common environment for all agents
QUANT_ENV = {
    "PYTHONPATH": "/home/nock/projects/quant_suite",
    "QUANT_RESULTS": "/home/nock/quant_results",
}
