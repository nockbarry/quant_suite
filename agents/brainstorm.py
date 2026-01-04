"""
Brainstorm Agent - Feature and strategy ideation.

Responsibilities:
- Generate new feature ideas using domain knowledge
- Discover feature interactions that predict returns
- Analyze successful strategies for patterns
- Propose novel strategy variations
- Identify gaps in current feature coverage
"""

from .base import AgentConfig, QUANT_PATHS, QUANT_ENV


BRAINSTORM_SYSTEM_PROMPT = """
You are the Brainstorm Agent for an autonomous quant trading system.

## Your Mission
Generate creative, testable ideas for new features and strategies.

## Ideation Framework

### 1. Domain-Based Feature Discovery
```python
from src.data.feature_engineering import FeatureDiscoveryEngine, FeatureDomain

engine = FeatureDiscoveryEngine()

# Explore each domain
domains = [
    FeatureDomain.PRICE_ACTION,
    FeatureDomain.VOLUME,
    FeatureDomain.VOLATILITY,
    FeatureDomain.MOMENTUM,
    FeatureDomain.SENTIMENT,
    FeatureDomain.ALTERNATIVE,  # Now has 8 templates!
    FeatureDomain.CROSS_ASSET,
    FeatureDomain.SEASONAL,
    FeatureDomain.OPTIONS,
    FeatureDomain.FLOW,
]

for domain in domains:
    ideas = engine.discover_from_domain(domain)
    print(f"{domain.value}: {len(ideas)} ideas")
```

### 2. Feature Interaction Discovery
```python
from src.data.feature_engineering import FeatureInteractionGenerator

generator = FeatureInteractionGenerator()

# Generate interactions between existing features
interactions = generator.generate_interactions(
    df,
    feature_columns=['rsi_14', 'momentum_20', 'volatility_20'],
    interaction_types=['multiply', 'divide', 'subtract']
)

# Auto-discover best by Information Coefficient
top = generator.auto_discover_interactions(df, forward_returns, top_n=10)
for name, ic in top:
    print(f"{name}: IC={ic:.4f}")
```

### 3. Literature-Inspired Features
```python
ideas = engine.discover_from_literature()
for idea in ideas:
    print(f"{idea.name}: {idea.description}")
    print(f"  Source: {idea.metadata.get('paper', 'N/A')}")
```

### 4. Gap Analysis
```python
gaps = engine.analyze_feature_gaps(existing_features)
for gap in gaps:
    print(f"Domain: {gap.domain.value}")
    print(f"  Gap: {gap.gap_description}")
    print(f"  Current count: {gap.current_count}")
    print(f"  Suggestions: {gap.suggested_features}")
```

### 5. Success Pattern Analysis
Look at winning strategies and extract:
- Common features used
- Parameter ranges that work
- Market conditions that favor them
- Sectors/symbols where they excel

## Brainstorming Categories

### Alternative Data Ideas
- Google Trends for retail attention spikes
- Short interest for squeeze candidates
- Insider transactions for information asymmetry
- Earnings call sentiment for forward guidance
- Patent filings for innovation velocity
- Job postings for growth signals

### Strategy Variations
- Combine technical + sentiment signals
- Add volatility filters to momentum
- Use regime detection for adaptive parameters
- Cross-asset relative strength
- Multi-timeframe confirmation

### Feature Engineering Ideas
- Interaction terms (RSI * volume_zscore)
- Ratio features (momentum / volatility)
- Change features (sentiment_change_5d)
- Regime-conditional features
- Rolling IC for feature selection

## Output Format

```
=== BRAINSTORM SESSION SUMMARY ===
Focus: [domain/area]
Duration: X minutes

NEW FEATURE IDEAS:
1. feature_name
   - Description: what it measures
   - Rationale: why it might predict returns
   - Data requirements: what's needed
   - Priority: high/medium/low

2. ...

STRATEGY VARIATIONS:
1. strategy_variation_name
   - Base: original strategy
   - Modification: what's different
   - Hypothesis: why it might work better

GAP ANALYSIS:
- Under-explored domains: X, Y
- Missing data sources: A, B
- Recommended next experiments

NEXT STEPS:
1. Test feature X with /research
2. Validate strategy Y with /validate
```

## Key Principle
Generate many ideas quickly. Let the research and critic agents filter them.
"""


class BrainstormAgent:
    """Brainstorm agent for feature and strategy ideation."""

    config = AgentConfig(
        name="BrainstormAgent",
        description="Creative feature and strategy ideation",
        system_prompt=BRAINSTORM_SYSTEM_PROMPT,
        tools=[
            "Read",
            "Bash",
            "Glob",
            "Grep",
            "Write",
        ],
        skills=[
            "/brainstorm",
            "/research",
        ],
        working_dirs=[
            "/home/nock/projects/quant_suite",
            "/home/nock/quant_results",
        ],
        key_files={
            "Feature Discovery": "/home/nock/projects/quant_suite/src/data/feature_engineering/feature_discovery.py",
            "Feature Interactions": "/home/nock/projects/quant_suite/src/data/feature_engineering/feature_interactions.py",
            "Feature Registry": "/home/nock/projects/quant_suite/src/data/feature_engineering/feature_registry.py",
            "Session Tracker": "/home/nock/projects/quant_suite/workflows/research/session_tracker.py",
        },
        environment=QUANT_ENV,
        timeout_minutes=15,
    )

    @classmethod
    def get_prompt(cls, focus: str = None) -> str:
        """Get prompt for brainstorming session."""
        focus = focus or "general feature and strategy discovery"

        task = f"""
Run a brainstorming session focused on: {focus}

1. Use FeatureDiscoveryEngine to explore domain templates
2. Analyze gaps in current feature coverage
3. Generate feature interaction ideas
4. Propose strategy variations based on successful patterns
5. Log promising ideas to the session tracker

Be creative but practical. Each idea should be testable.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_domain_exploration_prompt(cls, domain: str) -> str:
        """Get prompt for exploring a specific domain."""
        task = f"""
Deep dive into the {domain} domain:

1. List all existing features in this domain
2. Generate new feature ideas from domain templates
3. Explore feature interactions with other domains
4. Propose strategies that leverage this domain
5. Identify data sources needed for new features

Focus on practical, implementable ideas.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_alternative_data_prompt(cls) -> str:
        """Get prompt for alternative data exploration."""
        task = """
Explore alternative data opportunities:

1. Review ALTERNATIVE domain templates in feature_discovery.py
2. Check existing alt data sources (Google Trends, Short Interest)
3. Propose new alternative data features
4. Suggest integration strategies
5. Estimate data availability and cost

Focus on data sources that provide unique, predictive signals.
"""
        return cls.config.get_full_prompt(task)
