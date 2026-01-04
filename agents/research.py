"""
Research Agent - Comprehensive strategy research and testing.

Responsibilities:
- Run full research cycles across strategies and symbols
- Test hypotheses with proper statistical validation
- Identify promising strategy-symbol combinations
- Generate experiment leads for follow-up
- Log insights to session tracker
"""

from .base import AgentConfig, QUANT_PATHS, QUANT_ENV


RESEARCH_SYSTEM_PROMPT = """
You are the Research Agent for an autonomous quant trading system.

## Your Mission
Discover and validate alpha-generating strategies through rigorous testing.

## Research Protocol

### Phase 1: Inventory
1. Load current strategy definitions from config/strategies/validated_strategies.yaml
2. Check session tracker for recent experiments to avoid duplication
3. Identify untested strategy-symbol combinations

### Phase 2: Alternative Data Collection
```python
# Google Trends for retail attention
from src.data.sources.alternative import GoogleTrendsSource
trends = GoogleTrendsSource()
attention = trends.get_retail_attention('SYMBOL')

# Short interest for squeeze detection
from src.data.sources.alternative import ShortInterestSource
shorts = ShortInterestSource()
data = shorts.fetch_short_interest('SYMBOL')
```

### Phase 3: Strategy Testing
For each strategy-symbol pair:
```bash
PYTHONPATH=. timeout 120 python3 -c "
from workflows.research.comprehensive_researcher import ComprehensiveResearcher
researcher = ComprehensiveResearcher()
results = researcher.run_single_experiment('STRATEGY', 'SYMBOL')
print(f'Sharpe: {results.val_sharpe:.2f}, p-value: {results.mcpt_p_value:.4f}')
"
```

**IMPORTANT**: If a command fails or produces no output, do NOT retry more than twice.
Move on to the next symbol/strategy and note the failure in your report.

### Phase 4: Validation Criteria
A strategy PASSES if:
- MCPT p-value < 0.05 (statistically significant)
- Out-of-sample Sharpe > 0.5
- Sharpe CI lower bound > 0
- Survives 10bps transaction costs

### Phase 5: Insight Logging
```python
from workflows.research.session_tracker import get_tracker
tracker = get_tracker()

# Log successful strategy
tracker.log_experiment(
    strategy="strategy_name",
    symbol="SYMBOL",
    params={"param1": value},
    result="success",
    sharpe=2.5,
    p_value=0.01
)

# Log insight
tracker.log_insight(
    title="Key finding",
    description="Details",
    category="strategy",  # or 'feature', 'market', 'risk'
    evidence={"sharpe": 2.5},
    tags=["tag1", "tag2"]
)
```

## Output Format
Always end with a structured summary:
```
=== RESEARCH CYCLE SUMMARY ===
Experiments Run: N
Significant (p<0.05): M
Production Ready: K

TOP STRATEGIES:
1. strategy/SYMBOL - Sharpe: X.XX, p=0.XXXX
2. ...

NEXT LEADS:
1. Test X on Y because Z
2. ...

ARTIFACTS:
- /path/to/cycle_file.json
- /path/to/report.md
```

## Key Commands
```bash
# Full research cycle
PYTHONPATH=. timeout 300 python3 scripts/full_research_cycle.py --quick

# Single strategy test
PYTHONPATH=. timeout 120 python3 scripts/validate_strategy.py --strategy NAME --symbol SYMBOL

# Check recent cycles
ls -la /home/nock/quant_results/comprehensive_research/
```

## Error Handling
- Use `timeout 120` to prevent commands from hanging indefinitely
- If a command fails 2 times, skip it and move to the next experiment
- Record failures in your summary report
- Always use `python3` (not `python`)
"""


class ResearchAgent:
    """Research agent for strategy discovery and testing."""

    config = AgentConfig(
        name="ResearchAgent",
        description="Comprehensive strategy research and alpha discovery",
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        tools=[
            "Read",
            "Write",
            "Bash",
            "Glob",
            "Grep",
        ],
        skills=[
            "/research",
            "/validate",
            "/brainstorm",
        ],
        working_dirs=[
            "/home/nock/projects/quant_suite",
            "/home/nock/quant_results",
        ],
        key_files={
            "Strategies": QUANT_PATHS["strategies"] + "/validated_strategies.yaml",
            "Research Script": QUANT_PATHS["scripts"] + "/full_research_cycle.py",
            "Validation Script": QUANT_PATHS["scripts"] + "/validate_strategy.py",
            "Session Tracker": "/home/nock/projects/quant_suite/workflows/research/session_tracker.py",
            "Comprehensive Researcher": "/home/nock/projects/quant_suite/workflows/research/comprehensive_researcher.py",
        },
        environment=QUANT_ENV,
        timeout_minutes=45,
    )

    @classmethod
    def get_prompt(cls, task: str = None) -> str:
        """Get the full prompt for the research agent."""
        if task is None:
            task = "Run a comprehensive research cycle to discover alpha-generating strategies."
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_quick_research_prompt(cls, universes: list[str] = None, strategies: list[str] = None) -> str:
        """Get prompt for quick research on specific universes/strategies."""
        universes = universes or ["tech_mega", "semiconductors"]
        strategies = strategies or ["bollinger_reversal", "momentum", "rsi_reversal"]

        task = f"""
Run a focused research cycle with:
- Universes: {', '.join(universes)}
- Strategies: {', '.join(strategies)}

Focus on finding the best strategy-symbol combinations.
Log all results to the session tracker.
Generate a summary report with next steps.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_follow_up_prompt(cls, leads: list[dict]) -> str:
        """Get prompt for following up on research leads."""
        leads_text = "\n".join(
            f"- {l['title']}: {l.get('strategy', 'TBD')} on {', '.join(l.get('symbols', []))}"
            for l in leads
        )

        task = f"""
Follow up on these research leads from the previous cycle:

{leads_text}

For each lead:
1. Run the suggested experiments
2. Validate any promising results
3. Log insights to the tracker
4. Generate new leads based on findings
"""
        return cls.config.get_full_prompt(task)
