---
name: research
description: Run quantitative research cycles to discover and validate trading strategies. Use when asked to research strategies, test hypotheses, run experiments, or find alpha. Supports full cycles, quick tests, sector-specific research, and follow-up on leads.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, Edit
---

# Quant Research Skill

Run comprehensive research cycles to discover, test, and validate trading strategies.

## Quick Start

```bash
# Full research cycle (all strategies, all symbols)
PYTHONPATH=. python scripts/full_research_cycle.py

# Quick research (reduced scope for iteration)
PYTHONPATH=. python scripts/full_research_cycle.py --quick

# Sector-specific research
PYTHONPATH=. python scripts/full_research_cycle.py --sectors technology,financials

# Strategy-specific research
PYTHONPATH=. python scripts/full_research_cycle.py --strategies bollinger_reversal,momentum
```

## Research Phases

Every research cycle goes through these phases:

### Phase 1: Session Setup
```python
from workflows.research.research_protocol import ResearchProtocol, ResearchFocus
protocol = ResearchProtocol()
session = protocol.start_session(focus=ResearchFocus.STRATEGY_DEVELOPMENT)
```

### Phase 2: Feature Discovery
```python
from src.data.feature_engineering.feature_discovery import FeatureDiscoveryEngine
engine = FeatureDiscoveryEngine()
report = engine.generate_discovery_report()
# Returns: total_ideas, by_domain, top_features
```

### Phase 3: Alternative Data Collection
```python
from src.data.sources.alternative import GoogleTrendsSource, ShortInterestSource

# Retail attention signals
trends = GoogleTrendsSource()
attention = trends.get_retail_attention('NVDA')

# Short squeeze detection
shorts = ShortInterestSource()
squeeze = shorts.find_squeeze_candidates(['GME', 'AMC'], min_short_pct=0.15)
```

### Phase 4: Strategy Research
```python
from workflows.research.comprehensive_researcher import ComprehensiveResearcher
import asyncio

researcher = ComprehensiveResearcher()
results = asyncio.run(researcher.run_full_cycle(
    universes=['tech_mega', 'semiconductors', 'financials'],
    strategies=['bollinger_reversal', 'momentum', 'rsi_reversal']
))
```

### Phase 5: PDT Optimization
```python
from src.evaluation.validation.pdt_framework import PDTAwareBacktest, AccountType

backtest = PDTAwareBacktest(account_type=AccountType.BUDGET)
results = backtest.compare_holding_periods(signals, prices, [0, 2, 5, 10, 20])
```

### Phase 6: Insight Logging
```python
from workflows.research.session_tracker import get_tracker

tracker = get_tracker()
tracker.log_insight(
    title="Strategy discovery",
    description="Found significant edge",
    category="strategy",
    evidence={"sharpe": 2.5, "p_value": 0.01},
    tags=["bollinger", "semiconductors"]
)
```

## Available Components

### Strategies (11 total)
- bollinger_reversal, rsi_reversal, momentum, breakout
- sma_crossover, insider_momentum, insider_value
- sentiment_momentum, sentiment_reversal
- regime_adaptive, multi_signal

### Symbol Universes
- tech_mega: AAPL, MSFT, GOOGL, AMZN, META, NVDA
- semiconductors: NVDA, AMD, AVGO, QCOM, MU, MRVL, INTC
- financials: JPM, GS, V, MA
- healthcare: UNH, JNJ, LLY, MRNA
- energy: XOM, CVX
- market_etfs: SPY, QQQ, IWM, DIA

### Features (36 registered)
- Technical: rsi, bollinger_bands, macd, atr, momentum, volatility
- Sentiment: news_sentiment, social_sentiment
- Alternative: filing_sentiment, mda_tone
- Flow: options_put_call, insider_activity
- Risk: beta, drawdown, tail_risk
- Regime: market_regime, volatility_regime

## Output Locations

| Output | Path |
|--------|------|
| Research reports | `/home/nock/quant_results/full_research/` |
| Cycle results | `/home/nock/quant_results/comprehensive_research/` |
| Insights | `/home/nock/quant_results/research_tracker/insights.json` |
| Experiments | `/home/nock/quant_results/research_tracker/experiments.json` |

## Following Up on Leads

After a research cycle, check experiment_leads in the results:
```python
import json
with open('/home/nock/quant_results/comprehensive_research/cycle_YYYYMMDD_HHMMSS.json') as f:
    results = json.load(f)

for lead in results['experiment_leads'][:5]:
    print(f"{lead['title']}: {lead['symbols']} (priority: {lead['priority']})")
```

## Register Output as Document

Research outputs from the web dashboard are auto-indexed. For CLI research, register manually:

```python
from src.db.write_api import athena_db

athena_db.save_document(
    doc_type="research_result",
    title="Bollinger Reversal Research: Semiconductors",
    file_path=str(output_path),
    source="skill:research",
    symbols=["NVDA", "AMD", "QCOM", "MU"],
    tags=["research", "bollinger_reversal", "semiconductors"],
)
```

Session tracker insights and experiments are also indexed — they appear at `/documents/insights/list` and `/documents/experiments/list`.

## Query Historical Context

Before starting research, check what's already been discovered:

```python
from src.db.write_api import athena_db

# Previous research on this symbol
docs = athena_db.get_documents_for_symbol("NVDA", limit=10)

# Search insights for related work
insights = athena_db.search_insights("bollinger semiconductor")
for ins in insights:
    print(f"  [{ins.category}] {ins.title} (confidence: {ins.confidence})")

# Recent research documents
recent = athena_db.get_recent_documents(limit=10)
research = [d for d in recent if d.doc_type == "research_result"]
```

Or use the convenience script:
```bash
PYTHONPATH=. python3 scripts/context_for_symbol.py NVDA
```

## Validation Requirements

All strategies must pass before production:
- MCPT p-value < 0.05
- No lookahead bias detected
- Walk-forward OOS validation
- Sharpe ratio confidence interval

See `/validate` skill for full validation suite.
