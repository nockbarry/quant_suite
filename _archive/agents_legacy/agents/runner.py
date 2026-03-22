#!/usr/bin/env python3
"""
Agent Runner - Spawn and manage quant agents.

Usage:
    python agents/runner.py research --quick --universes tech_mega semiconductors
    python agents/runner.py critic --strategy bollinger_reversal --symbol QCOM
    python agents/runner.py monitor --check health
    python agents/runner.py brainstorm --focus alternative
    python agents/runner.py orchestrate --workflow full_cycle
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .base import AgentResult, AgentStatus, QUANT_PATHS
from .research import ResearchAgent
from .critic import CriticAgent
from .monitor import MonitorAgent
from .brainstorm import BrainstormAgent
from .orchestrator import OrchestratorAgent


def get_agent_prompt(agent_type: str, **kwargs) -> str:
    """Get the appropriate prompt for an agent type."""

    if agent_type == "research":
        universes = kwargs.get("universes", ["tech_mega", "semiconductors"])
        strategies = kwargs.get("strategies", ["bollinger_reversal", "momentum"])
        if kwargs.get("quick"):
            return ResearchAgent.get_quick_research_prompt(universes, strategies)
        return ResearchAgent.get_prompt()

    elif agent_type == "critic":
        strategy = kwargs.get("strategy")
        symbol = kwargs.get("symbol")
        if strategy and symbol:
            return CriticAgent.get_prompt(strategy, symbol)
        candidates = kwargs.get("candidates", [])
        if candidates:
            return CriticAgent.get_batch_validation_prompt(candidates)
        raise ValueError("Critic agent requires --strategy and --symbol, or --candidates")

    elif agent_type == "monitor":
        check = kwargs.get("check", "all")
        if check == "alerts":
            return MonitorAgent.get_alert_check_prompt()
        elif check == "performance":
            days = kwargs.get("days", 30)
            return MonitorAgent.get_performance_review_prompt(days)
        return MonitorAgent.get_prompt(check)

    elif agent_type == "brainstorm":
        focus = kwargs.get("focus", "general")
        if focus == "alternative":
            return BrainstormAgent.get_alternative_data_prompt()
        elif focus.startswith("domain:"):
            domain = focus.split(":")[1]
            return BrainstormAgent.get_domain_exploration_prompt(domain)
        return BrainstormAgent.get_prompt(focus)

    elif agent_type == "orchestrate":
        workflow = kwargs.get("workflow", "daily")
        if workflow == "full_cycle":
            return OrchestratorAgent.get_full_cycle_prompt()
        elif workflow == "validation":
            strategies = kwargs.get("strategies", [])
            return OrchestratorAgent.get_validation_pipeline_prompt(strategies)
        elif workflow == "emergency":
            issue = kwargs.get("issue", "Unknown issue")
            return OrchestratorAgent.get_emergency_response_prompt(issue)
        return OrchestratorAgent.get_daily_ops_prompt()

    else:
        raise ValueError(f"Unknown agent type: {agent_type}")


def save_agent_config(agent_type: str, prompt: str, output_dir: Path = None) -> Path:
    """Save agent configuration to file for reference."""
    if output_dir is None:
        output_dir = Path(QUANT_PATHS["results"]) / "agent_runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{agent_type}_{timestamp}.json"

    config = {
        "agent_type": agent_type,
        "timestamp": timestamp,
        "prompt": prompt,
        "status": "ready",
    }

    output_path = output_dir / filename
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)

    return output_path


def print_prompt(agent_type: str, prompt: str):
    """Print the agent prompt for use with Claude."""
    print("=" * 60)
    print(f"AGENT: {agent_type.upper()}")
    print("=" * 60)
    print()
    print(prompt)
    print()
    print("=" * 60)
    print("Copy the above prompt to spawn this agent.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Spawn quant agents")
    subparsers = parser.add_subparsers(dest="agent", help="Agent type")

    # Research agent
    research_parser = subparsers.add_parser("research", help="Research agent")
    research_parser.add_argument("--quick", action="store_true", help="Quick research mode")
    research_parser.add_argument("--universes", nargs="+", default=["tech_mega"], help="Symbol universes")
    research_parser.add_argument("--strategies", nargs="+", default=["bollinger_reversal"], help="Strategies to test")

    # Critic agent
    critic_parser = subparsers.add_parser("critic", help="Critic agent")
    critic_parser.add_argument("--strategy", help="Strategy name")
    critic_parser.add_argument("--symbol", help="Symbol")

    # Monitor agent
    monitor_parser = subparsers.add_parser("monitor", help="Monitor agent")
    monitor_parser.add_argument("--check", choices=["health", "alerts", "performance", "all"], default="all")
    monitor_parser.add_argument("--days", type=int, default=30, help="Days for performance review")

    # Brainstorm agent
    brainstorm_parser = subparsers.add_parser("brainstorm", help="Brainstorm agent")
    brainstorm_parser.add_argument("--focus", default="general", help="Focus area (alternative, domain:X, or general)")

    # Orchestrator agent
    orchestrate_parser = subparsers.add_parser("orchestrate", help="Orchestrator agent")
    orchestrate_parser.add_argument("--workflow", choices=["daily", "full_cycle", "validation", "emergency"], default="daily")
    orchestrate_parser.add_argument("--issue", help="Issue description for emergency workflow")

    # Common arguments
    parser.add_argument("--save", action="store_true", help="Save config to file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if not args.agent:
        parser.print_help()
        return 1

    try:
        prompt = get_agent_prompt(args.agent, **vars(args))

        if args.save:
            path = save_agent_config(args.agent, prompt)
            print(f"Saved to: {path}")

        if args.json:
            output = {
                "agent": args.agent,
                "prompt": prompt,
                "timestamp": datetime.now().isoformat(),
            }
            print(json.dumps(output, indent=2))
        else:
            print_prompt(args.agent, prompt)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
