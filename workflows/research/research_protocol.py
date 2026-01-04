"""Structured research protocol for Claude Code.

Provides a systematic approach to research with defined phases:
1. Gap Analysis - Identify under-explored areas
2. Hypothesis Generation - Create testable hypotheses
3. Experiment Design - Define experiments
4. Validation - Run and validate experiments
5. Insight Extraction - Record learnings
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ResearchPhase(Enum):
    """Research protocol phases."""

    GAP_ANALYSIS = "gap_analysis"
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    EXPERIMENT_DESIGN = "experiment_design"
    VALIDATION = "validation"
    INSIGHT_EXTRACTION = "insight_extraction"


class ResearchFocus(Enum):
    """Research focus areas."""

    FEATURE_DISCOVERY = "feature_discovery"
    STRATEGY_DEVELOPMENT = "strategy_development"
    PARAMETER_OPTIMIZATION = "parameter_optimization"
    SECTOR_ANALYSIS = "sector_analysis"
    ALTERNATIVE_DATA = "alternative_data"
    RISK_ANALYSIS = "risk_analysis"
    PDT_OPTIMIZATION = "pdt_optimization"


@dataclass
class ResearchHypothesis:
    """A testable research hypothesis."""

    id: str
    statement: str
    focus: ResearchFocus
    rationale: str
    test_criteria: str
    priority: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    tested: bool = False
    result: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "focus": self.focus.value,
            "rationale": self.rationale,
            "test_criteria": self.test_criteria,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "tested": self.tested,
            "result": self.result,
            "evidence": self.evidence,
        }


@dataclass
class ResearchInsight:
    """An insight discovered during research."""

    id: str
    title: str
    description: str
    focus: ResearchFocus
    evidence: dict[str, Any]
    actionable: bool = True
    implemented: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "focus": self.focus.value,
            "evidence": self.evidence,
            "actionable": self.actionable,
            "implemented": self.implemented,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class ResearchSession:
    """A research session with tracked progress."""

    session_id: str
    focus: ResearchFocus
    started_at: datetime = field(default_factory=datetime.now)
    current_phase: ResearchPhase = ResearchPhase.GAP_ANALYSIS
    hypotheses: list[ResearchHypothesis] = field(default_factory=list)
    insights: list[ResearchInsight] = field(default_factory=list)
    experiments_run: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    completed: bool = False
    ended_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "focus": self.focus.value,
            "started_at": self.started_at.isoformat(),
            "current_phase": self.current_phase.value,
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "insights": [i.to_dict() for i in self.insights],
            "experiments_run": self.experiments_run,
            "notes": self.notes,
            "completed": self.completed,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class ResearchProtocol:
    """
    Structured research protocol for systematic exploration.

    Guides Claude Code through research phases with prompts
    and tracking for each step.
    """

    # Phase-specific prompts for Claude Code
    PHASE_PROMPTS = {
        ResearchPhase.GAP_ANALYSIS: """
## Gap Analysis Phase

Analyze current coverage and identify gaps:

1. **Feature Coverage**: Run `FeatureDiscoveryEngine().analyze_gaps(current_features)`
2. **Strategy Coverage**: Check which strategy-symbol combinations are untested
3. **Sector Coverage**: Identify under-explored sectors
4. **Data Source Coverage**: Check for unused alternative data sources

Key questions:
- What domains have < 5 features?
- Which sectors haven't been tested with our best strategies?
- What alternative data sources are available but unused?
""",
        ResearchPhase.HYPOTHESIS_GENERATION: """
## Hypothesis Generation Phase

Generate testable hypotheses based on gaps:

1. **From Gaps**: Convert each gap into a testable hypothesis
2. **From Successes**: What made winning strategies work? Can we extend?
3. **From Literature**: Check `FeatureDiscoveryEngine().discover_from_literature()`
4. **From Domain Knowledge**: Sector-specific patterns

Format each hypothesis as:
- Statement: "Strategy X will show Sharpe > 1.0 on symbols Y"
- Rationale: Why this should work
- Test Criteria: How to validate (p-value, Sharpe threshold)
""",
        ResearchPhase.EXPERIMENT_DESIGN: """
## Experiment Design Phase

Design experiments to test hypotheses:

1. **Define Experiments**:
   - Strategy configuration
   - Symbol universe
   - Date range (use walk-forward)
   - Validation criteria (MCPT p < 0.05)

2. **Prioritize**:
   - High priority: High-confidence hypotheses, quick to test
   - Medium: Reasonable hypotheses, moderate effort
   - Low: Exploratory, uncertain outcomes

3. **Check Resources**:
   - Data availability
   - Compute requirements
   - Dependencies on other experiments
""",
        ResearchPhase.VALIDATION: """
## Validation Phase

Run experiments with rigorous validation:

1. **Execute Experiments**:
   ```python
   from workflows.research.comprehensive_researcher import ComprehensiveResearcher
   researcher = ComprehensiveResearcher()
   results = researcher.run_cycle(universes=['tech_mega'], strategies=['bollinger_reversal'])
   ```

2. **Validation Checks**:
   - MCPT p-value < 0.05
   - Walk-forward OOS Sharpe > 0.5
   - No lookahead bias
   - Sufficient trades (> 10)

3. **Record Results**: Update knowledge base with outcomes
""",
        ResearchPhase.INSIGHT_EXTRACTION: """
## Insight Extraction Phase

Extract and record learnings:

1. **Successful Experiments**:
   - What worked and why?
   - Can it be extended to other symbols/sectors?
   - What parameters were optimal?

2. **Failed Experiments**:
   - Why did it fail?
   - What did we learn?
   - Record to avoid repeating

3. **Patterns Observed**:
   - Cross-strategy patterns
   - Sector-specific behaviors
   - Regime dependencies

4. **Update Knowledge Base**:
   ```python
   from workflows.research.knowledge_base import KnowledgeBase
   kb = KnowledgeBase()
   kb.add_insight(insight)
   ```
""",
    }

    # Focus-specific guidance
    FOCUS_GUIDANCE = {
        ResearchFocus.FEATURE_DISCOVERY: """
### Feature Discovery Focus

Commands:
```python
from src.data.feature_engineering import FeatureDiscoveryEngine, FeatureInteractionGenerator

# Generate new feature ideas
engine = FeatureDiscoveryEngine(existing_features=current_features)
report = engine.generate_discovery_report()

# Auto-discover interactions
generator = FeatureInteractionGenerator()
interactions = generator.auto_discover_interactions(df, forward_returns, top_n=20)

# Check feature stability
from src.data.feature_engineering import FeatureStabilityMonitor
monitor = FeatureStabilityMonitor()
stability = monitor.generate_stability_report(df, features, returns)
```

Priority areas:
- Alternative data features (sentiment, trends, short interest)
- Cross-asset features (sector relative strength)
- Volatility regime features
""",
        ResearchFocus.STRATEGY_DEVELOPMENT: """
### Strategy Development Focus

Commands:
```python
from workflows.research.comprehensive_researcher import ComprehensiveResearcher

# Run comprehensive research
researcher = ComprehensiveResearcher()
results = researcher.run_cycle(
    universes=['tech_mega', 'market_etfs'],
    strategies=['bollinger_reversal', 'momentum', 'rsi_reversal']
)

# Check experiment leads
leads = results['experiment_leads']
```

Focus areas:
- Extend winning strategies to new symbols
- Test parameter variations
- Combine signals from multiple strategies
""",
        ResearchFocus.PDT_OPTIMIZATION: """
### PDT Optimization Focus

Commands:
```python
from src.evaluation.validation import PDTAwareBacktest, HoldingPeriodOptimizer, AccountType

# Compare holding periods
backtest = PDTAwareBacktest(account_type=AccountType.BUDGET)
results = backtest.compare_holding_periods(signals, prices, [0, 2, 5, 10, 20])

# Find optimal for budget accounts
optimizer = HoldingPeriodOptimizer(backtest)
optimizer.run_full_optimization(strategy_signals, strategy_prices)
budget_best = optimizer.get_best_for_budget_account()
```

Key questions:
- Which strategies work best with 2-day minimum hold?
- What's the Sharpe penalty for PDT compliance?
- Can we find strategies where longer holding improves results?
""",
        ResearchFocus.ALTERNATIVE_DATA: """
### Alternative Data Focus

Commands:
```python
# Google Trends
from src.data.sources.alternative import GoogleTrendsSource
trends = GoogleTrendsSource()
attention = trends.get_retail_attention('TSLA')

# Short Interest
from src.data.sources.alternative import ShortInterestSource
shorts = ShortInterestSource()
data = shorts.fetch_short_interest('AMC')

# FinBERT Sentiment
from src.strategies.alternative.sentiment import SentimentAnalyzer
analyzer = SentimentAnalyzer(model_name='finbert', force_transformer=True)
score, conf = analyzer.analyze(text)
```

Priority sources:
1. Google Trends (retail attention)
2. Short interest (squeeze potential)
3. FinBERT sentiment (news analysis)
4. Earnings calls (future: transcript NLP)
""",
    }

    def __init__(
        self,
        output_dir: str | Path = "/home/nock/quant_results/research_sessions",
    ):
        """
        Initialize research protocol.

        Args:
            output_dir: Directory to save session data
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: ResearchSession | None = None

    def start_session(
        self,
        focus: ResearchFocus,
        session_id: str | None = None,
    ) -> ResearchSession:
        """
        Start a new research session.

        Args:
            focus: Research focus area
            session_id: Optional session ID

        Returns:
            New ResearchSession
        """
        if session_id is None:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.current_session = ResearchSession(
            session_id=session_id,
            focus=focus,
        )

        logger.info(f"Started research session: {session_id} with focus: {focus.value}")
        return self.current_session

    def get_phase_prompt(self, phase: ResearchPhase | None = None) -> str:
        """Get the prompt for current or specified phase."""
        phase = phase or (self.current_session.current_phase if self.current_session else ResearchPhase.GAP_ANALYSIS)
        return self.PHASE_PROMPTS.get(phase, "")

    def get_focus_guidance(self, focus: ResearchFocus | None = None) -> str:
        """Get guidance for current or specified focus."""
        focus = focus or (self.current_session.focus if self.current_session else ResearchFocus.STRATEGY_DEVELOPMENT)
        return self.FOCUS_GUIDANCE.get(focus, "")

    def advance_phase(self) -> ResearchPhase:
        """Advance to next research phase."""
        if not self.current_session:
            raise ValueError("No active session")

        phases = list(ResearchPhase)
        current_idx = phases.index(self.current_session.current_phase)

        if current_idx < len(phases) - 1:
            self.current_session.current_phase = phases[current_idx + 1]
            logger.info(f"Advanced to phase: {self.current_session.current_phase.value}")
        else:
            logger.info("Already at final phase")

        return self.current_session.current_phase

    def add_hypothesis(
        self,
        statement: str,
        rationale: str,
        test_criteria: str,
        priority: float = 0.5,
    ) -> ResearchHypothesis:
        """Add a hypothesis to current session."""
        if not self.current_session:
            raise ValueError("No active session")

        hypothesis = ResearchHypothesis(
            id=f"hyp_{len(self.current_session.hypotheses) + 1:03d}",
            statement=statement,
            focus=self.current_session.focus,
            rationale=rationale,
            test_criteria=test_criteria,
            priority=priority,
        )

        self.current_session.hypotheses.append(hypothesis)
        logger.info(f"Added hypothesis: {hypothesis.id}")
        return hypothesis

    def record_hypothesis_result(
        self,
        hypothesis_id: str,
        result: str,
        evidence: dict[str, Any],
    ) -> None:
        """Record result for a hypothesis."""
        if not self.current_session:
            raise ValueError("No active session")

        for hyp in self.current_session.hypotheses:
            if hyp.id == hypothesis_id:
                hyp.tested = True
                hyp.result = result
                hyp.evidence = evidence
                logger.info(f"Recorded result for {hypothesis_id}: {result}")
                return

        logger.warning(f"Hypothesis {hypothesis_id} not found")

    def add_insight(
        self,
        title: str,
        description: str,
        evidence: dict[str, Any],
        actionable: bool = True,
    ) -> ResearchInsight:
        """Add an insight to current session."""
        if not self.current_session:
            raise ValueError("No active session")

        insight = ResearchInsight(
            id=f"ins_{len(self.current_session.insights) + 1:03d}",
            title=title,
            description=description,
            focus=self.current_session.focus,
            evidence=evidence,
            actionable=actionable,
        )

        self.current_session.insights.append(insight)
        logger.info(f"Added insight: {insight.title}")
        return insight

    def add_note(self, note: str) -> None:
        """Add a note to current session."""
        if not self.current_session:
            raise ValueError("No active session")

        self.current_session.notes.append(f"[{datetime.now().isoformat()}] {note}")

    def record_experiment(self, experiment_id: str) -> None:
        """Record that an experiment was run."""
        if not self.current_session:
            raise ValueError("No active session")

        self.current_session.experiments_run.append(experiment_id)

    def end_session(self) -> dict[str, Any]:
        """End current session and save."""
        if not self.current_session:
            raise ValueError("No active session")

        self.current_session.completed = True
        self.current_session.ended_at = datetime.now()

        # Save session
        output_path = self.output_dir / f"{self.current_session.session_id}.json"
        with open(output_path, "w") as f:
            json.dump(self.current_session.to_dict(), f, indent=2)

        logger.info(f"Session saved to {output_path}")

        summary = self.current_session.to_dict()
        self.current_session = None
        return summary

    def generate_session_prompt(self) -> str:
        """Generate a complete prompt for the current session."""
        if not self.current_session:
            return "No active session. Start one with `protocol.start_session(focus)`"

        prompt = f"""
# Research Session: {self.current_session.session_id}
**Focus**: {self.current_session.focus.value}
**Phase**: {self.current_session.current_phase.value}
**Started**: {self.current_session.started_at.strftime('%Y-%m-%d %H:%M')}

---

{self.get_phase_prompt()}

---

{self.get_focus_guidance()}

---

## Session Progress
- Hypotheses: {len(self.current_session.hypotheses)}
- Experiments Run: {len(self.current_session.experiments_run)}
- Insights: {len(self.current_session.insights)}

## Next Steps
1. Complete current phase tasks
2. Record findings with `add_insight()` or `record_hypothesis_result()`
3. Advance to next phase with `advance_phase()`
"""
        return prompt


def quick_research_prompt(focus: str = "strategy") -> str:
    """
    Generate a quick research prompt for common tasks.

    Args:
        focus: One of 'strategy', 'feature', 'pdt', 'alternative'

    Returns:
        Research prompt string
    """
    prompts = {
        "strategy": """
## Quick Strategy Research

```bash
PYTHONPATH=. python -m workflows.research.comprehensive_researcher \\
    --universes tech_mega semiconductors \\
    --strategies bollinger_reversal momentum rsi_reversal
```

Check results in `/home/nock/quant_results/comprehensive_research/`
""",
        "feature": """
## Quick Feature Discovery

```python
from src.data.feature_engineering import FeatureDiscoveryEngine, FeatureDomain

engine = FeatureDiscoveryEngine()
# Get ideas for specific domain
ideas = engine.discover_from_domain(FeatureDomain.SENTIMENT)
# Get literature-inspired ideas
lit_ideas = engine.discover_from_literature()
# Full report
report = engine.generate_discovery_report()
```
""",
        "pdt": """
## Quick PDT Analysis

```python
from src.evaluation.validation import PDTAwareBacktest, HoldingPeriodOptimizer, AccountType

backtest = PDTAwareBacktest(account_type=AccountType.BUDGET)
results = backtest.compare_holding_periods(signals, prices, [0, 2, 5, 10, 20])

# Find best for budget account
for r in results:
    if r.pdt_compliant:
        print(f"{r.holding_period_days}d: Sharpe={r.sharpe_ratio:.2f}")
```
""",
        "alternative": """
## Quick Alternative Data Check

```python
# Google Trends
from src.data.sources.alternative import GoogleTrendsSource
trends = GoogleTrendsSource()
attention = trends.get_retail_attention('TSLA')
print(f"TSLA attention z-score: {attention.zscore:.2f}")

# Short Interest
from src.data.sources.alternative import ShortInterestSource
shorts = ShortInterestSource()
data = shorts.fetch_short_interest('GME')
print(f"GME short %: {data.short_percent_of_float:.1%}")
```
""",
    }

    return prompts.get(focus, prompts["strategy"])
