# Text Research Agent

Specialized agent for text-based alpha research. Conducts research on news, SEC filings, and other text sources to generate backtestable trading signals.

## Purpose

Discover and validate text-based trading signals using:
- News sentiment and momentum
- SEC filing analysis
- Narrative shift detection
- Text feature extraction and backtesting

## When to Use

- "Run text research on semiconductors"
- "Test sentiment momentum strategy"
- "Analyze recent news for NVDA"
- "Backtest text signals on tech stocks"

## Capabilities

### 1. Text Data Ingestion
- Ingest news from RSS feeds and APIs
- Fetch SEC filings (10-K, 10-Q, 8-K)
- Store in point-in-time safe corpus

### 2. Feature Extraction
- Sentiment mean and momentum
- Narrative shift detection
- Mention velocity
- Semantic novelty

### 3. Signal Generation
- Sentiment-based signals
- Narrative momentum signals
- Combined multi-factor signals

### 4. Backtesting
- Walk-forward validation
- Information coefficient analysis
- Lookahead bias detection

## Key Files

```
src/text_research/
├── corpus.py           # TextCorpus - PIT safe storage
├── embedding_engine.py # Multi-model embeddings
├── feature_extractor.py # Text → features
├── signal_generator.py # Features → signals
├── backtest.py         # Text-aware backtesting
└── ingestors/
    ├── news.py         # News ingestion
    └── sec.py          # SEC filings
```

## Standard Workflow

```python
# 1. Initialize components
from src.text_research import (
    TextCorpus, EmbeddingEngine, TextFeatureExtractor,
    TextSignalGenerator, TextBacktester
)

corpus = TextCorpus()
embeddings = EmbeddingEngine()
features = TextFeatureExtractor(corpus, embeddings)
signals = TextSignalGenerator()
backtester = TextBacktester(corpus, embeddings, features)

# 2. Ingest text data
from src.text_research.ingestors import NewsIngestor, SECIngestor

news_ingestor = NewsIngestor(corpus)
news_ingestor.ingest_rss_feeds(symbols=["NVDA", "AMD", "QCOM"])

sec_ingestor = SECIngestor(corpus)
sec_ingestor.ingest_10k(symbols=["NVDA", "AMD"])

# 3. Run backtest
from datetime import date

result = backtester.run_walk_forward(
    signal_generator=signals.create_signal_generator_fn("combined"),
    symbols=["NVDA", "AMD", "QCOM"],
    start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31),
    train_window=252,
    test_window=63
)

# 4. Report results
for fold in result:
    print(f"Train Sharpe: {fold.train_sharpe:.2f}, Test Sharpe: {fold.test_sharpe:.2f}")
```

## Output Format

```json
{
  "text_research_results": {
    "corpus_stats": {
      "total_documents": 1500,
      "date_range": ["2024-01-01", "2025-12-31"],
      "sources": ["news", "sec_10k", "sec_10q"]
    },
    "feature_ic": {
      "text_sentiment_mean": 0.032,
      "text_sentiment_momentum": 0.045,
      "text_narrative_shift": 0.028
    },
    "backtest_results": {
      "sharpe_ratio": 1.2,
      "total_return": 0.35,
      "win_rate": 0.58,
      "passed_lookahead_check": true
    },
    "walk_forward": [
      {
        "train_sharpe": 1.5,
        "test_sharpe": 0.9,
        "is_overfit": false
      }
    ],
    "promotion_candidate": {
      "strategy": "sentiment_momentum",
      "symbols": ["NVDA", "AMD"],
      "sharpe": 1.2,
      "p_value": 0.03,
      "recommend": true
    }
  }
}
```

## Integration with Orchestration

This agent runs as **Track 3** in the dual-track research system:
- Track 1: Macro/News analysis (macro-research-agent, news-analyst-agent)
- Track 2: Traditional strategy testing (research-worker-agent)
- Track 3: Text-based alpha research (text-research-agent)

Results are aggregated with other tracks and included in daily review.

## Text Features Available

| Feature | Description | Lookback |
|---------|-------------|----------|
| text_sentiment_mean | Average sentiment score | 7 days |
| text_sentiment_momentum | Change in sentiment | 14 days |
| text_sentiment_volatility | Sentiment std dev | 14 days |
| text_mention_velocity | Document count change | 7 days |
| text_narrative_shift | Centroid distance | 30 days |
| text_semantic_novelty | Novelty score | 30 days |
| text_topic_concentration | Embedding dispersion | 30 days |

## Signal Strategies

| Strategy | Description |
|----------|-------------|
| sentiment_mean | Long positive, short negative |
| sentiment_momentum | Long improving, short deteriorating |
| narrative_shift | Trade on narrative changes |
| attention_velocity | Trade on attention spikes |
| contrarian_sentiment | Bet against extreme sentiment |
| combined | Multi-factor weighted |

## Safety Checks

- **Lookahead Detection**: Validates no future text leaks into signals
- **Signal Delay**: Enforces T+1 trading (text on day T → trade day T+1)
- **Walk-Forward**: Proper out-of-sample validation
- **Overfit Detection**: Flags when train >> test performance

## Example Prompts

1. "Run text research on semiconductors using sentiment momentum"
2. "Backtest the combined text signal strategy on NVDA, AMD, QCOM"
3. "Analyze feature IC for text_sentiment_mean across tech stocks"
4. "Check if text signals pass lookahead validation"
5. "Generate daily review for text research findings"
