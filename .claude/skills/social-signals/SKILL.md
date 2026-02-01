---
name: social-signals
description: Check social signal landscape across WSB, Stocktwits, and other platforms. Surfaces early signals, trending mentions, and thesis suggestions.
---

# Social Signals Skill

Check the social signal landscape for early alpha opportunities.

## Purpose

Scan social platforms (Reddit WSB, Stocktwits) for:
- Early signals before they go mainstream
- Trending stocks with unusual activity
- Signal convergence (multiple platforms agreeing)
- Thesis suggestions based on converging signals

## Usage

```bash
claude "/social-signals"              # Full social scan
claude "/social-signals NVDA MU"      # Check specific symbols
claude "/social-signals --trending"   # Just trending
claude "/social-signals --early"      # Just early signals
```

## What This Skill Does

1. **Scan WSB** - Check Reddit WallStreetBets for:
   - Mention frequency and trends
   - DD (due diligence) posts
   - Sentiment analysis
   - Signal "vintage" (days since first detection)

2. **Scan Stocktwits** - Check Stocktwits for:
   - Message volume
   - Bull/bear ratio
   - Watcher counts
   - Trending symbols

3. **Detect Convergences** - Find symbols where:
   - Multiple platforms agree
   - Signal is still early (< 7 days, < 100 mentions)
   - Growing momentum

4. **Suggest Theses** - When 3+ signals converge:
   - Auto-generate thesis suggestion
   - Include suggested signposts
   - Calculate confidence score

## Workflow

```python
# 1. Scan social platforms
from src.data.sources.alternative.wsb_tracker import get_wsb_tracker
from src.data.sources.alternative.stocktwits import get_stocktwits_client

wsb = get_wsb_tracker()
stocktwits = get_stocktwits_client()

# 2. Get early signals
await wsb.scan_recent_posts()
early_signals = wsb.get_early_signals()

# 3. Check trending
trending = stocktwits.get_trending()

# 4. Generate thesis suggestions
from src.knowledge.thesis_suggester import get_thesis_suggester
suggester = get_thesis_suggester()
suggestions = suggester.generate_suggestions()
```

## Output Format

```
SOCIAL SIGNALS REPORT
═══════════════════════════════════════════════════════════════

EARLY SIGNALS (Potential Alpha)
─────────────────────────────────────────
  📈 WDC    | vintage: 5d | growth: +45% | mentions: 127
  📈 SOUN   | vintage: 3d | growth: +82% | mentions: 89
  📉 NKLA   | vintage: 6d | growth: +23% | mentions: 156

TRENDING (High Volume)
─────────────────────────────────────────
  🔥 NVDA   | bull: 72% | msgs: 450 | watchers: 125K
  🔥 TSLA   | bull: 58% | msgs: 380 | watchers: 200K

THESIS SUGGESTIONS
─────────────────────────────────────────
📈 WDC: WDC Spin-off Catalyst
   Confidence: 75% | Signals: 4 | Sources: wsb, stocktwits, options
   Summary: Multiple signals point to spin-off value unlocking
   Actions: [Accept] [Dismiss] [Watch]

═══════════════════════════════════════════════════════════════
```

## Signal Phase Classification

| Phase | Criteria | Action |
|-------|----------|--------|
| EARLY | < 7 days, < 100 mentions/day | High alpha potential, research more |
| GROWING | Growth > 20%/day | Momentum building, consider entry |
| MAINSTREAM | > 500 mentions/day, news coverage | Alpha may be captured, late entry |
| PEAKED | Mentions declining > 20% | Exit or avoid |

## Integration with Other Skills

- **Before /morning-briefing**: Run /social-signals to check overnight social activity
- **Before /trade-decision**: Include social signals in decision context
- **With /thesis**: Accept thesis suggestions from social convergences

## Signal Provenance

Every social signal gets tracked:
```python
from src.knowledge.signal_provenance import create_signal_provenance

# Creates provenance record linked back to source
signal = create_signal_provenance(
    source="wsb",
    symbol="WDC",
    confidence=0.7,
    direction="bullish",
    description="Spin-off DD gaining traction",
    detection_method="mention_spike",
)
```

## Best Practices

1. **Check daily** - Social signals move fast
2. **Cross-validate** - Don't act on single-source signals
3. **Respect vintage** - Early signals have more alpha potential
4. **Track outcomes** - Use provenance to learn which sources work

## Data Sources

| Source | Update Frequency | Rate Limit |
|--------|-----------------|------------|
| Reddit WSB | On-demand | 60 req/min |
| Stocktwits | On-demand | 200 req/hr |
| Twitter/X | Not yet implemented | - |

## Files

- `src/data/sources/alternative/wsb_tracker.py` - Reddit tracking
- `src/data/sources/alternative/stocktwits.py` - Stocktwits API
- `src/data/sources/alternative/social_timeseries.py` - Time series DB
- `src/knowledge/signal_provenance.py` - Signal tracking
- `src/knowledge/thesis_suggester.py` - Thesis suggestions
