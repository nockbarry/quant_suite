---
name: brainstorm
description: Generate new feature and strategy ideas through structured brainstorming. Use when looking for new alpha sources, exploring feature interactions, analyzing gaps in coverage, or ideating novel approaches. Combines domain knowledge, literature, and data-driven discovery.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, WebSearch
---

# Brainstorm Skill

Systematic ideation for features, strategies, and alpha sources.

## Quick Start

```bash
# Feature discovery report
PYTHONPATH=. python -c "
from src.data.feature_engineering.feature_discovery import FeatureDiscoveryEngine
engine = FeatureDiscoveryEngine()
report = engine.generate_discovery_report()
print(f'Total ideas: {report[\"total_ideas\"]}')
for domain, ideas in report['by_domain'].items():
    print(f'  {domain}: {len(ideas)} ideas')
"

# Gap analysis
PYTHONPATH=. python -c "
from src.data.feature_engineering.feature_discovery import FeatureDiscoveryEngine, FeatureDomain
engine = FeatureDiscoveryEngine()
gaps = engine.discover_from_domain(FeatureDomain.SENTIMENT)
print(f'Sentiment gaps: {len(gaps)} ideas')
"
```

## Brainstorming Modes

### 1. Domain-Based Discovery

Explore specific domains for new feature ideas:

```python
from src.data.feature_engineering.feature_discovery import FeatureDiscoveryEngine, FeatureDomain

engine = FeatureDiscoveryEngine()

# Available domains
domains = [
    FeatureDomain.SENTIMENT,      # News, social, analyst ratings
    FeatureDomain.VOLATILITY,     # Vol surfaces, term structure
    FeatureDomain.CROSS_ASSET,    # Correlations, spreads
    FeatureDomain.MICROSTRUCTURE, # Order flow, bid-ask
    FeatureDomain.MACRO,          # Economic indicators
    FeatureDomain.SEASONALITY,    # Calendar effects
    FeatureDomain.ALTERNATIVE,    # Alt data sources
    FeatureDomain.BEHAVIORAL,     # Retail vs institutional
    FeatureDomain.TECHNICAL,      # Price patterns
    FeatureDomain.FUNDAMENTAL,    # Earnings, valuations
]

for domain in domains:
    ideas = engine.discover_from_domain(domain)
    print(f"\n{domain.name}:")
    for idea in ideas[:3]:
        print(f"  - {idea['name']}: {idea['description']}")
```

### 2. Literature-Inspired Features

Academic research-backed ideas:

```python
from src.data.feature_engineering.feature_discovery import LITERATURE_FEATURES

print("Literature-inspired features:")
for name, spec in LITERATURE_FEATURES.items():
    print(f"\n{name}:")
    print(f"  Source: {spec['source']}")
    print(f"  Description: {spec['description']}")
    print(f"  Complexity: {spec['complexity']}")
```

### 3. Feature Interaction Discovery

Automatically find valuable feature combinations:

```python
from src.data.feature_engineering.feature_interactions import FeatureInteractionGenerator
import pandas as pd

generator = FeatureInteractionGenerator()

# Auto-discover best interactions by Information Coefficient
top_interactions = generator.auto_discover_interactions(
    df=feature_df,
    forward_returns=returns,
    top_n=20
)

print("Top feature interactions:")
for interaction in top_interactions:
    print(f"  {interaction['name']}: IC={interaction['ic']:.3f}")
```

### 4. Gap Analysis

Find under-explored areas:

```python
from src.data.feature_engineering.feature_registry import get_registry_summary

summary = get_registry_summary()
print("Current coverage:")
for category, count in summary['by_category'].items():
    print(f"  {category}: {count} features")

# Identify gaps
gaps = []
if summary['by_category'].get('fundamental', 0) < 5:
    gaps.append("FUNDAMENTAL: Need more earnings/valuation features")
if summary['by_category'].get('sentiment', 0) < 10:
    gaps.append("SENTIMENT: Need more news/social features")

print("\nGaps identified:")
for gap in gaps:
    print(f"  - {gap}")
```

### 5. Strategy Brainstorming

Generate new strategy ideas:

```python
def brainstorm_strategies(focus_area):
    """
    Generate strategy ideas for a focus area.
    """
    ideas = {
        "mean_reversion": [
            {
                "name": "Bollinger + Volume Confirmation",
                "description": "Mean reversion with volume spike confirmation",
                "hypothesis": "Volume confirms genuine reversions vs noise",
                "test": "Add volume condition to bollinger_reversal"
            },
            {
                "name": "RSI Divergence",
                "description": "Price makes new low but RSI doesn't",
                "hypothesis": "Divergence signals exhaustion",
                "test": "Implement divergence detection"
            }
        ],
        "momentum": [
            {
                "name": "Sector Rotation Momentum",
                "description": "Go long strongest sector, short weakest",
                "hypothesis": "Sector momentum persists",
                "test": "Compare sector ETFs"
            },
            {
                "name": "Earnings Momentum",
                "description": "Long stocks beating estimates",
                "hypothesis": "PEAD (Post-Earnings Announcement Drift)",
                "test": "Track earnings surprises"
            }
        ],
        "alternative_data": [
            {
                "name": "Retail Attention Contrarian",
                "description": "Fade extreme Google Trends spikes",
                "hypothesis": "Retail arrives late to moves",
                "test": "Track Trends z-score extremes"
            },
            {
                "name": "Short Squeeze Momentum",
                "description": "Long high-short stocks with positive momentum",
                "hypothesis": "Squeezes create explosive moves",
                "test": "Filter by short interest + price action"
            }
        ]
    }

    return ideas.get(focus_area, [])
```

## Brainstorming Session Protocol

### Step 1: Define Focus

```python
focus_areas = [
    "sentiment_features",      # NLP, news, social
    "cross_asset_features",    # Correlations, spreads
    "microstructure_features", # Order flow
    "strategy_improvements",   # Enhance existing
    "new_alpha_sources",       # Novel approaches
]
```

### Step 2: Gather Context

```python
from workflows.research.session_tracker import get_tracker

tracker = get_tracker()

# What's worked before?
successful = tracker.get_successful_strategies(min_sharpe=1.0)
print(f"Successful patterns: {len(successful)}")

# What's failed?
failed = tracker.get_failed_combinations()
print(f"Failed combinations: {len(failed)}")

# Existing insights
insights = tracker.search_insights(category="feature")
```

### Step 3: Generate Ideas

```python
session_ideas = []

# Domain exploration
for domain in [FeatureDomain.SENTIMENT, FeatureDomain.ALTERNATIVE]:
    ideas = engine.discover_from_domain(domain)
    session_ideas.extend(ideas)

# Literature review
lit_ideas = engine.discover_from_literature()
session_ideas.extend(lit_ideas)

# Interaction discovery
if feature_df is not None:
    interactions = generator.auto_discover_interactions(feature_df, returns, top_n=10)
    session_ideas.extend(interactions)
```

### Step 4: Prioritize

```python
def prioritize_ideas(ideas):
    """
    Score and prioritize ideas.
    """
    scored = []
    for idea in ideas:
        score = 0

        # Novelty (not already implemented)
        if idea['name'] not in existing_features:
            score += 2

        # Data availability
        if idea.get('data_available', True):
            score += 1

        # Complexity (prefer simpler)
        complexity = idea.get('complexity', 'medium')
        score += {'low': 2, 'medium': 1, 'high': 0}.get(complexity, 1)

        # Expected IC
        expected_ic = idea.get('expected_ic', 0.02)
        score += expected_ic * 50

        scored.append({**idea, 'priority_score': score})

    return sorted(scored, key=lambda x: x['priority_score'], reverse=True)
```

### Step 5: Document & Track

```python
def log_brainstorm_session(session_id, ideas, focus_area):
    """
    Log brainstorming session for future reference.
    """
    tracker = get_tracker()

    tracker.log_insight(
        title=f"Brainstorm session: {focus_area}",
        description=f"Generated {len(ideas)} ideas",
        category="feature",
        evidence={
            "session_id": session_id,
            "focus": focus_area,
            "top_ideas": ideas[:5],
            "total_ideas": len(ideas)
        },
        tags=["brainstorm", focus_area]
    )

    # Save full session
    output_path = Path(f"~/quant_results/brainstorm_sessions/{session_id}.json")
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "session_id": session_id,
            "focus": focus_area,
            "generated_at": datetime.now().isoformat(),
            "ideas": ideas
        }, f, indent=2)
```

## Idea Templates

### Feature Idea
```python
{
    "name": "google_trends_momentum",
    "description": "Week-over-week change in search volume",
    "domain": "alternative",
    "hypothesis": "Rising search interest precedes price moves",
    "data_source": "Google Trends via pytrends",
    "complexity": "low",
    "expected_ic": 0.03,
    "implementation": "trends_df.pct_change(7).rolling(30).mean()",
    "priority": "high"
}
```

### Strategy Idea
```python
{
    "name": "sentiment_divergence",
    "description": "Trade when sentiment and price diverge",
    "hypothesis": "Sentiment leads price by 1-3 days",
    "entry": "Long when sentiment positive but price declining",
    "exit": "Price catches up or 5-day timeout",
    "universe": ["NVDA", "TSLA", "AMD"],
    "expected_sharpe": 1.5,
    "risk": "Sentiment data lag"
}
```

## Output Locations

| Output | Path |
|--------|------|
| Brainstorm sessions | `~/quant_results/brainstorm_sessions/` |
| Feature ideas | `~/quant_results/feature_ideas/` |
| Discovery reports | `~/quant_results/discovery_reports/` |
