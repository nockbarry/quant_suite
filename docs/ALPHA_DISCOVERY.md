# Alpha Discovery System

Autonomous alpha discovery from novel data sources.

**Core Question**: "Where does information asymmetry exist?"

---

## Architecture

```
+------------------------------------------------------------------+
|                  ALPHA DISCOVERY ORCHESTRATOR                     |
|           "Where does information asymmetry exist?"               |
+--------------------------------+---------------------------------+
                                 |
        +------------------------+------------------------+
        |                        |                        |
        v                        v                        v
+---------------+       +---------------+       +---------------+
| MARKET SCANNER|       | DATA ACQUIRER |       |  HYPOTHESIS   |
|               |       |               |       |   PIPELINE    |
| Find where    |       | Scrape blogs  |       |               |
| alpha exists  |       | Free APIs     |       | Idea -> Test  |
| Rank opps     |       | ETF proxies   |       | Auto validate |
+---------------+       +---------------+       +---------------+
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/data/sources/universal/free_api_hub.py` | FRED API + ETF proxies for commodities |
| `src/data/sources/universal/commodity_scraper.py` | DRAM, semi equipment, specialty commodities |
| `src/data/sources/universal/blog_scraper.py` | Semi Analysis, Stratechery RSS scraping |
| `src/data/synthesis/llm_extractor.py` | Extract insights from text |
| `src/alpha_discovery/market_scanner.py` | Scan for inefficiencies |
| `workflows/alpha_discovery/idea_to_strategy.py` | Full automation pipeline |
| `workflows/research/knowledge_base.py` | Track data source alpha, causal relationships |

---

## Commodity Data (Free)

```python
from src.data.sources.universal import FreeAPIHub, CommoditySource
import asyncio

# Get commodity via ETF proxy
hub = FreeAPIHub()
gold = asyncio.run(hub.get_commodity('gold', days=90))
print(f"Gold prices: {len(gold)} observations via GLD ETF")

# Get DRAM prices (MU as proxy)
source = CommoditySource()
dram = asyncio.run(source.get_dram_prices(days=90))

# Analyze lead-lag relationship
corr = asyncio.run(source.analyze_commodity_stock_lag('dram', ['NVDA', 'AMD'], days=180))
print(corr.nlargest(5, 'correlation'))  # DRAM leads AMD by 0.91 @ -18 days!
```

**Available Commodities** (via ETF proxies):
- gold (GLD), silver (SLV), oil (USO), natural_gas (UNG)
- copper (CPER), agriculture (DBA), uranium (URA)
- dram (MU), semi_equipment (AMAT/LRCX/KLAC/ASML composite)

---

## Blog Scraping

```python
from src.data.sources.universal import BlogScraper
import asyncio

scraper = BlogScraper()

# List available sources
print(scraper.list_sources())
# {'semianalysis': {...}, 'stratechery': {...}, 'asymco': {...}}

# Scrape Semi Analysis
articles = asyncio.run(scraper.scrape_source('semianalysis', max_articles=10))
for a in articles[:3]:
    print(f"{a.title}")
    print(f"  Symbols: {a.related_symbols}")
    print(f"  Published: {a.published_date}")

# Get articles for backtesting (point-in-time safe)
from datetime import datetime
pit_articles = scraper.get_articles_for_backtesting(
    as_of=datetime(2025, 6, 1)
)
```

---

## Insight Extraction

```python
from src.data.synthesis import extract_from_text, LLMExtractor

# Quick extraction (rule-based)
insights = extract_from_text(
    "NVDA expects 30% revenue growth as AI demand surges. "
    "Supply shortage of HBM memory easing.",
    source="article"
)
for i in insights:
    print(f"{i.signal_type.value}: {i.direction.value} on {i.symbols}")

# Generate research ideas from insights
extractor = LLMExtractor()
ideas = extractor.generate_hypotheses(insights)
for idea in ideas:
    print(f"Hypothesis: {idea.hypothesis}")
    print(f"  Priority: {idea.priority:.2f}")
```

---

## Market Scanner

```python
from src.alpha_discovery import MarketScanner
import asyncio

scanner = MarketScanner()

# Scan all universes
result = asyncio.run(scanner.scan_all())
print(f"Scanned {result.symbols_scanned} symbols")
print(f"Found {len(result.inefficiencies_found)} opportunities")

# Get research priorities
for p in scanner.get_research_priorities(5):
    print(f"{p['symbol']}: {p['type']}")
    print(f"  Direction: {p['direction']}, Edge: {p['expected_edge']*100:.1f}%")
    print(f"  Strategy: {p['suggested_strategy']}")

# Available scans:
# - scan_momentum_anomalies()
# - scan_mean_reversion()
# - scan_volume_divergence()
# - scan_sector_rotation()
```

---

## Idea-to-Strategy Pipeline

```python
from workflows.alpha_discovery import IdeaToStrategyPipeline, IdeaInput
import asyncio

# Define a hypothesis
idea = IdeaInput(
    hypothesis="DRAM prices lead semiconductor stocks",
    target_assets=["MU", "NVDA", "AMD"],
    strategy_types=["momentum", "mean_reversion"],
)

# Test automatically
pipeline = IdeaToStrategyPipeline()
result = asyncio.run(pipeline.test_idea(idea))

print(f"Status: {result.status.value}")
print(f"Best feature: {result.best_feature}")
print(f"Best IC: {result.best_ic:.4f}")
print(f"Best strategy: {result.best_strategy}")
print(f"Sharpe: {result.val_sharpe:.2f}")
print(f"MCPT p-value: {result.mcpt_pvalue:.4f}")
print(f"Significant: {result.is_significant}")
```

---

## Enhanced Knowledge Base

Track which data sources provide alpha:

```python
from workflows.research.knowledge_base import KnowledgeBase

kb = KnowledgeBase()

# Record data source performance
kb.record_data_source_performance(
    source='semianalysis',
    source_type='blog',
    prediction_correct=True,
    alpha_generated=0.05,
    strategy_name='momentum',
    sharpe=1.8,
    symbols=['NVDA', 'AMD']
)

# Get best data sources
for ds in kb.get_valuable_data_sources():
    print(f"{ds.source}: {ds.hit_rate:.1%} hit rate, {ds.cumulative_alpha:.2%} alpha")

# Record causal relationship
kb.record_causal_relationship(
    cause='dram_prices',
    effect='semiconductor_stocks',
    lag_days=5,
    correlation=0.42,
    p_value=0.02,
    mechanism='DRAM pricing power flows to chip manufacturers'
)

# Get leading indicators for a symbol
indicators = kb.get_leading_indicators('MU')
for ind in indicators:
    print(f"{ind['cause']} -> MU: lag={ind['lag_days']}d, r={ind['correlation']:.2f}")

# Get research suggestions from causal relationships
suggestions = kb.suggest_research_from_relationships()
```

---

## Alternative Data Sources

### Google Trends (Retail Attention)

```python
from src.data.sources.alternative import GoogleTrendsSource

trends = GoogleTrendsSource()
attention = trends.get_retail_attention('TSLA')

print(f"Z-score: {attention.zscore:.2f}")
print(f"Signal: {attention.signal}")  # 'high_attention', 'low_attention', 'normal'
print(f"Contrarian buy: {attention.is_contrarian_buy()}")
```

### Short Interest (Squeeze Detection)

```python
from src.data.sources.alternative import ShortInterestSource

shorts = ShortInterestSource()
data = shorts.fetch_short_interest('GME')

print(f"Short % of float: {data.short_percent_of_float:.1%}")
print(f"Days to cover: {data.short_ratio:.1f}")
print(f"Squeeze candidate: {data.is_squeeze_candidate()}")

# Find squeeze candidates
candidates = shorts.find_squeeze_candidates(['AMC', 'GME', 'BBBY'], min_short_pct=0.15)
```

### FinBERT Sentiment

```python
from src.strategies.alternative.sentiment import SentimentAnalyzer

# Force transformer mode (no lexicon fallback)
analyzer = SentimentAnalyzer(model_name='finbert', force_transformer=True)
score, confidence = analyzer.analyze("Stock surged on strong earnings")
print(f"Sentiment: {score:.2f}, Confidence: {confidence:.2f}")
```

---

## Sample Workflow

```
User: "Test if DRAM prices predict semiconductor stocks"

1. DATA-ACQUISITION-AGENT
   -> Fetches DRAM prices via MU proxy
   -> Stores with point-in-time timestamps

2. HYPOTHESIS-GENERATOR-AGENT
   -> Creates testable hypothesis
   -> Specifies test methodology

3. IDEA-TO-STRATEGY-PIPELINE
   -> Generates features
   -> Tests IC: 0.08, lag = 5 days
   -> Builds strategies
   -> Validates with MCPT

4. KNOWLEDGE-BASE records
   -> Source: dram_proxy with +4.2% alpha
   -> Causal: dram_prices -> semiconductors (5 day lag)

5. Output:
   "DRAM prices DO predict semiconductor stocks.
    Best strategy: Long MU when 7-day DRAM change > 3%
    Sharpe: 1.8, p-value: 0.02"
```

---

## CLI Quick Commands

```bash
# Scan for market opportunities
PYTHONPATH=. python -c "
import asyncio
from src.alpha_discovery import MarketScanner
scanner = MarketScanner()
result = asyncio.run(scanner.scan_all(universes=['semiconductors', 'tech_mega']))
print(f'Found {len(result.inefficiencies_found)} opportunities')
for p in scanner.get_research_priorities(5):
    print(f'  {p[\"symbol\"]}: {p[\"type\"]} ({p[\"direction\"]})')
"

# Scrape industry blogs
PYTHONPATH=. python -c "
import asyncio
from src.data.sources.universal import BlogScraper
scraper = BlogScraper()
articles = asyncio.run(scraper.scrape_source('semianalysis', max_articles=5))
for a in articles:
    print(f'{a.title[:50]}... Symbols: {a.related_symbols}')
"

# Test a hypothesis
PYTHONPATH=. python -c "
import asyncio
from workflows.alpha_discovery import test_hypothesis
result = asyncio.run(test_hypothesis('Momentum on semiconductors', ['NVDA', 'AMD']))
print(f'Sharpe: {result.val_sharpe:.2f}, p-value: {result.mcpt_pvalue:.4f}')
"
```

---

*Last updated: 2026-01-05*
