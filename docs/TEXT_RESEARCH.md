# Text Research Framework

Point-in-time safe text-based alpha research system.

**Module Location**: `src/text_research/`

---

## Core Components

| Module | Description |
|--------|-------------|
| `corpus.py` | `TextCorpus` - PIT-safe document storage |
| `embedding_engine.py` | `EmbeddingEngine` - Multi-model embeddings |
| `feature_extractor.py` | `TextFeatureExtractor` - 7 text features |
| `signal_generator.py` | `TextSignalGenerator` - 6 signal strategies |
| `backtest.py` | `TextBacktester` - Walk-forward with proper temporal alignment |
| `ingestors/news.py` | `NewsIngestor` - RSS and API news |
| `ingestors/sec.py` | `SECIngestor` - 10-K, 10-Q, 8-K filings |

---

## Text Features

| Feature | Description | Lookback |
|---------|-------------|----------|
| `text_sentiment_mean` | Average sentiment score | 7 days |
| `text_sentiment_momentum` | Change in sentiment | 14 days |
| `text_sentiment_volatility` | Sentiment std dev | 14 days |
| `text_mention_velocity` | Document count change | 7 days |
| `text_narrative_shift` | Centroid distance | 30 days |
| `text_semantic_novelty` | Novelty score | 30 days |
| `text_topic_concentration` | Embedding dispersion | 30 days |

---

## Signal Strategies

| Strategy | Description |
|----------|-------------|
| `sentiment_mean` | Long positive, short negative sentiment |
| `sentiment_momentum` | Long improving, short deteriorating |
| `narrative_shift` | Trade on narrative changes |
| `attention_velocity` | Trade on attention spikes |
| `contrarian_sentiment` | Bet against extreme sentiment |
| `combined` | Multi-factor weighted |

---

## Usage

```python
from src.text_research import (
    TextCorpus, EmbeddingEngine, TextFeatureExtractor,
    TextSignalGenerator, TextBacktester
)
from src.text_research.ingestors import NewsIngestor, SECIngestor
from datetime import date

# Initialize components
corpus = TextCorpus()
embeddings = EmbeddingEngine()
features = TextFeatureExtractor(corpus, embeddings)
signals = TextSignalGenerator()
backtester = TextBacktester(corpus, embeddings, features)

# Ingest text data
news_ingestor = NewsIngestor(corpus)
news_ingestor.ingest_rss_feeds(symbols=["NVDA", "AMD", "QCOM"])

sec_ingestor = SECIngestor(corpus)
sec_ingestor.ingest_10k(symbols=["NVDA", "AMD"])

# Run walk-forward backtest
result = backtester.run_walk_forward(
    signal_generator=signals.create_signal_generator_fn("combined"),
    symbols=["NVDA", "AMD", "QCOM"],
    start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31),
    train_window=252,
    test_window=63
)

# Check for lookahead bias
is_clean = backtester.validate_no_lookahead()
print(f"Lookahead-free: {is_clean}")

# Print results
for fold in result:
    print(f"Train Sharpe: {fold.train_sharpe:.2f}, Test Sharpe: {fold.test_sharpe:.2f}")
```

---

## Key Design Principles

- **signal_delay=1**: Same-day text generates next-day signals (no lookahead)
- **Point-in-time safe**: All queries respect document timestamps
- **Walk-forward validation**: Proper temporal splits
- **Online learning**: Daily embedding updates without full recompute

---

## Feature Engineering System

### Feature Discovery

```python
from src.data.feature_engineering import FeatureDiscoveryEngine, FeatureDomain

engine = FeatureDiscoveryEngine(existing_features=['rsi', 'macd'])

# Get domain-specific ideas
ideas = engine.discover_from_domain(FeatureDomain.SENTIMENT)

# Get literature-inspired ideas
lit_ideas = engine.discover_from_literature()

# Full discovery report
report = engine.generate_discovery_report()
```

### Feature Interactions

```python
from src.data.feature_engineering import FeatureInteractionGenerator

generator = FeatureInteractionGenerator()

# Generate all interactions
result = generator.generate_interactions(df, feature_columns=['rsi', 'momentum', 'volatility'])

# Auto-discover best interactions by IC
top_interactions = generator.auto_discover_interactions(df, forward_returns, top_n=20)
```

### Feature Stability Monitoring

```python
from src.data.feature_engineering import FeatureStabilityMonitor

monitor = FeatureStabilityMonitor()

# Analyze single feature
report = monitor.analyze_feature(df, 'rsi_14', forward_returns)
print(f"IC: {report.ic_mean:.3f}, Grade: {report.grade}, Stable: {report.is_stable}")

# Full portfolio report
portfolio = monitor.generate_stability_report(df, ['rsi_14', 'macd', 'momentum'], forward_returns)
```

---

## Research Protocol

### Starting a Research Session

```python
from workflows.research.research_protocol import ResearchProtocol, ResearchFocus

protocol = ResearchProtocol()
session = protocol.start_session(focus=ResearchFocus.STRATEGY_DEVELOPMENT)

# Get phase-specific guidance
print(protocol.get_phase_prompt())
print(protocol.get_focus_guidance())
```

### Research Phases

1. **Gap Analysis** - Identify under-explored areas
2. **Hypothesis Generation** - Create testable hypotheses
3. **Experiment Design** - Define experiments
4. **Validation** - Run and validate experiments
5. **Insight Extraction** - Record learnings

### Session Tracker (Cross-Session Insights)

```python
from workflows.research.session_tracker import get_tracker

tracker = get_tracker()

# Log an insight
tracker.log_insight(
    title="Bollinger reversal works on semiconductors",
    description="QCOM, MU, MRVL all show Sharpe > 2.0",
    category="strategy",
    evidence={"sharpe": 2.5, "p_value": 0.01},
    tags=["bollinger", "semiconductors"]
)

# Log an experiment
tracker.log_experiment(
    strategy="bollinger_reversal",
    symbol="AVGO",
    params={"period": 20, "num_std": 2.0},
    result="success",
    sharpe=1.8,
    p_value=0.02
)

# Search past insights
insights = tracker.search_insights(category="strategy", min_confidence=0.6)
```

---

## Integration Components

### Strategy Promoter

**Location**: `workflows/promotion/strategy_promoter.py`

Semi-automatic promotion from research to production:

```bash
# Scan for candidates
PYTHONPATH=. python -m workflows.promotion.strategy_promoter scan

# List pending
PYTHONPATH=. python -m workflows.promotion.strategy_promoter list

# Approve and promote
PYTHONPATH=. python -m workflows.promotion.strategy_promoter approve all
PYTHONPATH=. python -m workflows.promotion.strategy_promoter promote
```

### Knowledge Base Feedback Loop

The daily runner now records to knowledge base:
- Live signals generated
- Execution results (fill price, slippage)
- Daily summaries

### Unified StrategySpec

**Location**: `src/core/strategy_spec.py`

Bridge between research and production:

```python
from src.core.strategy_spec import StrategySpec

# From experiment
spec = StrategySpec.from_experiment(
    strategy_name='my_strategy',
    symbol='AAPL',
    params={'rsi_period': 14},
    train_sharpe=1.5,
    val_sharpe=1.2,
    p_value=0.01,
)

# To YAML config
yaml_str = spec.to_yaml()
```

---

*Last updated: 2026-01-05*
