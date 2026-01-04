"""
Orchestrator Agent - Coordinates multi-agent workflows.

Responsibilities:
- Manage agent lifecycles and dependencies
- Route tasks to appropriate agents
- Aggregate results across agents
- Handle failures and retries
- Generate consolidated reports
"""

from .base import AgentConfig, QUANT_PATHS, QUANT_ENV


ORCHESTRATOR_SYSTEM_PROMPT = """
You are the Orchestrator Agent for an autonomous quant trading system.

## Your Mission
Coordinate specialized agents to run comprehensive quant workflows.

## Agent Fleet

| Agent | Purpose | Trigger |
|-------|---------|---------|
| ResearchAgent | Strategy discovery | New research cycle needed |
| CriticAgent | Safety validation | Strategy needs validation |
| MonitorAgent | Trading oversight | Performance check needed |
| BrainstormAgent | Feature ideation | New ideas needed |

## Standard Workflows

### 1. Full Research Cycle
```
1. BrainstormAgent -> Generate feature ideas
2. ResearchAgent -> Test strategies with new features
3. CriticAgent -> Validate promising strategies
4. MonitorAgent -> Update tracking with results
```

### 2. Strategy Validation Pipeline
```
1. ResearchAgent -> Initial testing
2. CriticAgent -> Full validation suite
3. CriticAgent -> Code review (if needed)
4. MonitorAgent -> Log results
```

### 3. Daily Operations
```
1. MonitorAgent -> Check system status
2. MonitorAgent -> Review performance
3. BrainstormAgent -> Generate new ideas (weekly)
4. ResearchAgent -> Follow up on leads
```

### 4. Emergency Response
```
1. MonitorAgent -> Detect anomaly
2. MonitorAgent -> Full diagnostic
3. CriticAgent -> Validate strategy behavior
4. (Human) -> Decide on action
```

## Spawning Agents

To spawn an agent, use the Task tool with:
- subagent_type: "general-purpose" (for complex reasoning)
- prompt: Agent's configured prompt
- description: Short description

Example:
```
Task(
    subagent_type="general-purpose",
    prompt=ResearchAgent.get_quick_research_prompt(["tech_mega"], ["bollinger_reversal"]),
    description="Quick research on tech strategies"
)
```

## Parallel vs Sequential

### Run in Parallel When:
- Agents don't depend on each other's output
- Testing multiple independent hypotheses
- Gathering information from multiple sources

### Run Sequentially When:
- One agent's output feeds another
- Validation depends on research results
- Order matters for correctness

## Result Aggregation

After all agents complete, aggregate results:

```python
results = {
    "research": research_agent_result,
    "critic": critic_agent_result,
    "monitor": monitor_agent_result,
}

# Extract key metrics
strategies_found = len(results["research"]["findings"])
validated = sum(1 for f in results["research"]["findings"] if results["critic"]["approved"])
```

## Error Handling

1. **Agent Timeout**: Retry with reduced scope
2. **Agent Failure**: Log error, continue with other agents
3. **Validation Failure**: Route to human review
4. **Data Unavailable**: Use cached data or skip

## Output Format

```
=== ORCHESTRATION SUMMARY ===
Workflow: [workflow name]
Started: YYYY-MM-DD HH:MM
Completed: YYYY-MM-DD HH:MM

AGENTS EXECUTED:
1. [Agent Name] - [Status] - [Duration]
   Summary: [one-line summary]

2. ...

CONSOLIDATED RESULTS:
- Strategies Tested: N
- Strategies Validated: M
- New Insights: K
- Alerts: L

KEY FINDINGS:
1. Finding 1
2. Finding 2

NEXT STEPS:
1. Follow-up action 1
2. Follow-up action 2

ARTIFACTS:
- /path/to/report1.md
- /path/to/report2.json
```

## Key Principle
Coordinate efficiently. Minimize redundant work across agents.
"""


class OrchestratorAgent:
    """Orchestrator agent for multi-agent coordination."""

    config = AgentConfig(
        name="OrchestratorAgent",
        description="Multi-agent workflow coordination",
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        tools=[
            "Read",
            "Write",
            "Bash",
            "Glob",
            "Grep",
            "Task",
            "TaskOutput",
        ],
        skills=[
            "/research",
            "/critic",
            "/monitor",
            "/brainstorm",
            "/report",
        ],
        working_dirs=[
            "/home/nock/projects/quant_suite",
            "/home/nock/quant_results",
        ],
        key_files={
            "Agent Configs": "/home/nock/projects/quant_suite/agents",
            "Session Tracker": "/home/nock/projects/quant_suite/workflows/research/session_tracker.py",
            "Research Results": QUANT_PATHS["research"],
            "Validation Results": QUANT_PATHS["validation"],
        },
        environment=QUANT_ENV,
        timeout_minutes=60,
    )

    @classmethod
    def get_full_cycle_prompt(cls) -> str:
        """Get prompt for full research cycle orchestration."""
        task = """
Orchestrate a full research cycle:

## Phase 1: Ideation (Parallel)
Spawn BrainstormAgent to:
- Generate feature ideas
- Identify gaps in current coverage

## Phase 2: Research (Parallel)
Spawn ResearchAgent to:
- Test strategies across universes
- Run MCPT validation
- Log results to tracker

## Phase 3: Validation (Sequential)
For each promising strategy, spawn CriticAgent to:
- Run full validation suite
- Detect any biases or issues

## Phase 4: Reporting
- Aggregate all results
- Generate consolidated report
- Log insights to tracker
- Identify next steps

Spawn agents in parallel where possible for efficiency.
Wait for results and aggregate before proceeding to dependent phases.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_validation_pipeline_prompt(cls, strategies: list[dict]) -> str:
        """Get prompt for validating multiple strategies."""
        strategies_text = "\n".join(
            f"- {s['strategy']}/{s['symbol']}: Sharpe={s.get('sharpe', 'N/A')}"
            for s in strategies
        )

        task = f"""
Run validation pipeline on these strategies:

{strategies_text}

For each strategy:
1. Spawn CriticAgent for validation
2. Collect results
3. Rank by confidence

Run validations in parallel where possible.
Provide consolidated ranking at the end.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_daily_ops_prompt(cls) -> str:
        """Get prompt for daily operations check."""
        task = """
Run daily operations workflow:

1. Spawn MonitorAgent to:
   - Check system health
   - Review recent performance
   - Identify any alerts

2. If alerts found, spawn additional diagnostics

3. Check session tracker for pending follow-ups

4. Generate daily summary report

Prioritize quick checks and flag anything needing attention.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_emergency_response_prompt(cls, issue: str) -> str:
        """Get prompt for emergency response."""
        task = f"""
Emergency response for: {issue}

1. Immediately spawn MonitorAgent to:
   - Full system diagnostic
   - Identify scope of issue

2. If strategy-related, spawn CriticAgent to:
   - Validate strategy behavior
   - Check for any anomalies

3. Compile findings for human review

4. Recommend immediate actions

Priority: URGENT - Complete quickly and thoroughly.
"""
        return cls.config.get_full_prompt(task)
