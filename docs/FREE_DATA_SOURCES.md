# Free Data Sources Implementation Guide

**Created**: 2026-01-10
**Reason**: Expand signal diversity by +30% at $0 cost by implementing 20+ free data sources

---

## Overview

This document details the implementation of free data sources added to Project Athena. The goal was to activate Claude's latent knowledge about market dynamics by providing structured access to publicly available data.

### Implementation Rationale

1. **Cost Efficiency**: All sources are completely free (government data, public websites, free API tiers)
2. **Signal Diversity**: Each source provides independent signals for better ensemble performance
3. **Latent Knowledge Activation**: Claude understands COT reports, AAII sentiment, VIX structure - now it can use that knowledge
4. **Point-in-Time Safety**: All data is timestamped for accurate backtesting
5. **Graceful Degradation**: System continues if individual sources fail

---

## Implementation Summary

### Files Created (2026-01-10)

| File | Category | Lines | Description |
|------|----------|-------|-------------|
| `vix_structure.py` | Market Regime | ~150 | CBOE VIX term structure signals |
| `put_call.py` | Market Regime | ~120 | Put/call ratio sentiment |
| `finviz_screens.py` | Market Regime | ~200 | Pre-built stock screener results |
| `aaii_sentiment.py` | Sentiment | ~100 | Retail investor weekly sentiment |
| `newsletter_sentiment.py` | Sentiment | ~90 | Advisor sentiment (Investors Intelligence) |
| `cot_report.py` | Sentiment | ~180 | CFTC Commitment of Traders data |
| `earnings_calendar.py` | Economic | ~150 | Earnings dates with whisper numbers |
| `economic_calendar.py` | Economic | ~200 | BLS, Fed, Treasury release schedule |
| `fed_futures.py` | Economic | ~140 | CME FedWatch rate probabilities |
| `treasury_calendar.py` | Economic | ~130 | Treasury auction schedule |
| `ipo_calendar.py` | Events | ~120 | NASDAQ IPO calendar |
| `fda_calendar.py` | Events | ~160 | FDA PDUFA dates, AdCom meetings |
| `patent_filings.py` | Innovation | ~180 | USPTO patent activity by company |
| `job_postings.py` | Innovation | ~150 | Job posting growth signals |
| `app_rankings.py` | Innovation | ~170 | App Store/Play rankings |
| `github_activity.py` | Innovation | ~160 | GitHub organization metrics |
| `collection_daemon.py` | Infrastructure | ~250 | Orchestrates all data collection |

---

## Data Source Details

### 0. Market Mover Scanner (`src/intelligence/market_movers.py`)

**Purpose**: Scan broad universe (~231 symbols) for significant price moves, enrich with multi-source context, feed signal provenance pipeline

**Data Source**: yfinance batch download (prices), existing cached JSON (news, Finviz screens, WSB, theses)

**Key Outputs**:
- `~/quant_results/live/market_movers_latest.json` — Latest scan results
- `~/quant_results/logs/market_movers_history.json` — 30-day history
- Documents in athena.db (`doc_type="market_mover"`) — Per-mover context records
- Signal provenance entries — Feeds convergence detection

**Universe Sources**: Portfolio positions, thesis vehicles, Finviz screens, WSB trending, SPY/QQQ holdings, research universe

**Thresholds**:
- Day move: >3% (intraday: >2%)
- Week move: >10% (intraday: >8%)
- Month move: >20% (intraday: >15%)
- Volume spike: >2x average (intraday: >1.5x)

**Context Enrichment**:
- News headline matches (thesis keyword index)
- Finviz screen membership
- WSB signal status (phase, mentions, sentiment)
- Thesis alignment (name, conviction)
- Context score: magnitude\*0.3 + news\*0.25 + finviz\*0.15 + thesis\*0.15 + wsb\*0.1 + volume\*0.05

**Schedule**: 12:30 PM (midday intraday) + 5:20 PM (after close) via `scripts/cron_market_movers.py`

**Web Dashboard**: `/movers` — Tabs for Top Context, Gainers, Losers, Volume Spikes; detail view per symbol

---

### 1. Market Regime Sources

#### VIX Term Structure (`vix_structure.py`)

**Purpose**: Detect market fear and mean-reversion opportunities

**Data Source**: CBOE delayed quotes

**Key Signals**:
- `slope`: (VIX 6M - VIX spot) / VIX spot
- `structure`: "steep_contango", "flat", "backwardation"
- `mean_reversion_signal`: -1 (sell vol) to +1 (buy vol)

**Trading Application**:
- Steep contango → Normal market, sell vol premium
- Backwardation → Fear spike, potential reversal coming
- Flat → Uncertain, reduce position sizing

```python
@dataclass
class VIXTermStructure:
    timestamp: datetime
    vix_spot: float
    vix_1m: float
    vix_3m: float
    vix_6m: float
    slope: float
    structure: str  # "steep_contango", "flat", "backwardation"
    mean_reversion_signal: float  # -1 to +1
    days_in_current_regime: int
```

**Update Frequency**: 15 minutes (market hours)

---

#### Put/Call Ratio (`put_call.py`)

**Purpose**: Contrarian sentiment indicator

**Data Source**: CBOE daily statistics

**Key Signals**:
- `equity_ratio`: Equity options put/call
- `index_ratio`: Index options put/call
- `percentile_30d`: Where current sits historically
- `contrarian_signal`: -1 to +1

**Trading Application**:
- High put/call (>1.1) → Extreme fear → Contrarian bullish
- Low put/call (<0.6) → Extreme greed → Contrarian bearish

```python
@dataclass
class PutCallData:
    timestamp: datetime
    total_ratio: float
    equity_ratio: float
    index_ratio: float
    percentile_30d: float
    signal: str  # "extreme_fear", "fear", "neutral", "greed", "extreme_greed"
    contrarian_signal: float
```

**Update Frequency**: 60 minutes (market hours)

---

#### Finviz Screens (`finviz_screens.py`)

**Purpose**: Pre-built screens for momentum, breakouts, oversold bounces

**Data Source**: Finviz free screener

**Available Screens**:
- `momentum_leaders`: Strong earnings + uptrend + above SMA20
- `volume_breakouts`: High volume + new 52-week highs
- `oversold_bounce`: RSI < 30 + positive change
- `earnings_winners`: Beat estimates + gap up
- `insider_buying`: Recent insider purchases

```python
SCREEN_DEFINITIONS = {
    "momentum_leaders": "v=111&f=fa_epsqoq_o15,ta_perf_dup,ta_sma20_pa&ft=4",
    "volume_breakouts": "v=111&f=sh_avgvol_o500,ta_change_u5,ta_highlow52w_nh",
    "oversold_bounce": "v=111&f=ta_rsi_os30,ta_change_u",
    ...
}
```

**Update Frequency**: 4 hours

---

### 2. Sentiment Extreme Sources

#### AAII Sentiment (`aaii_sentiment.py`)

**Purpose**: Retail investor sentiment (famous contrarian indicator)

**Data Source**: AAII.com weekly survey

**Key Signals**:
- `bullish_pct`, `bearish_pct`, `neutral_pct`
- `bull_bear_spread`: bullish - bearish
- `percentile_bullish`: Historical context
- `contrarian_signal`: -1 to +1

**Trading Application**:
- Bullish > 50% → Contrarian bearish (retail too optimistic)
- Bearish > 50% → Contrarian bullish (retail too pessimistic)
- Bull-bear spread extremes are powerful signals

```python
@dataclass
class AAIISentiment:
    survey_date: datetime
    bullish_pct: float
    neutral_pct: float
    bearish_pct: float
    bull_bear_spread: float
    historical_avg_bullish: float = 37.5
    percentile_bullish: float
    contrarian_signal: float
```

**Update Frequency**: Weekly (Thursday release)

---

#### COT Report (`cot_report.py`)

**Purpose**: Track commercial hedgers vs speculators

**Data Source**: CFTC weekly Commitment of Traders

**Key Insight**: Commercial hedgers (producers, processors) have real exposure and tend to be right at extremes. Speculators tend to be wrong at extremes.

**Key Signals**:
- `commercial_net`: Net commercial position
- `commercial_percentile`: Where commercials sit historically
- `signal`: Follow commercials at extremes

```python
@dataclass
class COTPosition:
    symbol: str  # ES, NQ, CL, GC, etc.
    report_date: datetime
    commercial_long: int
    commercial_short: int
    commercial_net: int
    speculator_net: int
    commercial_percentile: float
    extreme_reading: bool
    signal: float  # -1 to +1
```

**Trading Application**:
- Commercials extremely long (>90th percentile) → Bullish
- Commercials extremely short (<10th percentile) → Bearish
- Most useful for commodities and index futures

**Update Frequency**: Weekly (Friday release)

---

### 3. Economic Calendar Sources

#### Earnings Calendar (`earnings_calendar.py`)

**Purpose**: Know when earnings happen, with whisper numbers

**Data Source**: EarningsWhispers, Yahoo Finance

**Key Fields**:
- `report_time`: BMO (before market open), AMC (after market close)
- `eps_estimate` vs `eps_whisper`: Street whisper often more accurate
- `historical_move_avg`: How much does this stock typically move?
- `implied_move`: What options are pricing

```python
@dataclass
class EarningsEvent:
    symbol: str
    report_date: datetime
    report_time: str  # "BMO", "AMC"
    eps_estimate: float
    eps_whisper: float
    historical_move_avg: float
    implied_move: float
```

**Trading Application**:
- Avoid holding through earnings unless thesis-driven
- Use implied vs historical move for options plays
- Whisper numbers often more important than consensus

**Update Frequency**: 6 hours

---

#### Fed Futures (`fed_futures.py`)

**Purpose**: Market-implied Fed rate expectations

**Data Source**: CME FedWatch

**Key Signals**:
- `prob_hike`, `prob_cut`, `prob_hold` for next meeting
- `implied_rate_3m/6m/12m`: Forward rate expectations
- `rate_path_signal`: "hawkish", "dovish", "neutral"

```python
@dataclass
class FedExpectations:
    timestamp: datetime
    current_rate: float
    next_meeting_date: datetime
    prob_hike: float
    prob_cut: float
    prob_hold: float
    implied_rate_3m: float
    implied_rate_6m: float
    implied_rate_12m: float
    rate_path_signal: str
```

**Trading Application**:
- Dovish surprise → Tech, growth, rate-sensitive
- Hawkish surprise → Value, banks, commodities
- Changes in probabilities move markets

**Update Frequency**: 60 minutes (market hours)

---

### 4. Event Catalyst Sources

#### FDA Calendar (`fda_calendar.py`)

**Purpose**: Track binary biotech events

**Data Source**: FDA.gov, BioPharmCatalyst

**Event Types**:
- `PDUFA`: FDA decision deadline (most important)
- `AdCom`: Advisory committee meeting
- `Phase 3 data`: Clinical trial results

**Key Fields**:
- `estimated_approval_probability`: Historical rates by indication
- `is_binary_event`: True for PDUFA/AdCom

```python
APPROVAL_RATES = {
    "oncology": 0.35,
    "cardiovascular": 0.55,
    "infectious_disease": 0.60,
    "rare_disease": 0.45,
    "other": 0.50,
}

@dataclass
class FDAEvent:
    company: str
    symbol: str
    drug_name: str
    indication: str
    event_type: str  # "PDUFA", "AdCom", "Phase 3"
    expected_date: datetime
    estimated_approval_probability: float
    is_binary_event: bool
```

**Trading Application**:
- Position before PDUFA if thesis supports
- Binary events = defined risk options plays
- Be aware of portfolio exposure to biotech catalysts

**Update Frequency**: 12 hours

---

### 5. Innovation Signal Sources

#### Patent Filings (`patent_filings.py`)

**Purpose**: Track R&D activity as leading indicator

**Data Source**: USPTO API (free)

**Key Signals**:
- `patents_filed/granted` in period
- `yoy_change`: Year-over-year activity change
- `acceleration_signal`: Is innovation accelerating?

```python
@dataclass
class PatentActivity:
    company: str
    symbol: str
    period: str  # "30d", "90d"
    patents_filed: int
    patents_granted: int
    yoy_change: float
    key_technologies: list[str]
    acceleration_signal: float  # -1 to +1
```

**Trading Application**:
- Accelerating patents → Company investing in future
- Decelerating patents → Potential concern
- Best for tech/pharma/industrial companies

**Update Frequency**: Weekly

---

#### GitHub Activity (`github_activity.py`)

**Purpose**: Track developer ecosystem health

**Data Source**: GitHub API (60 req/hr free)

**Key Signals**:
- `total_stars`, `stars_change_30d`: Developer interest
- `contributors_active_30d`: Ecosystem health
- `developer_interest_signal`: -1 to +1

```python
COMPANY_ORGS = {
    "MSFT": "microsoft",
    "GOOGL": "google",
    "META": "facebook",
    "NVDA": "nvidia",
    "AMD": "amd",
    # ... more tech companies
}

@dataclass
class GitHubActivity:
    org_name: str
    symbol: str
    public_repos: int
    total_stars: int
    stars_change_30d: int
    contributors_active_30d: int
    developer_interest_signal: float
```

**Trading Application**:
- Growing stars/contributors → Healthy ecosystem
- Declining activity → Potential concern
- Compare to competitors within sector

**Update Frequency**: Daily

---

## Collection Daemon

### Purpose

Orchestrate all data source collection with:
- Configurable update frequencies
- Market hours awareness
- Graceful failure handling
- Rate limiting
- Cached storage with timestamps

### Schedule Configuration

```python
SCHEDULES = {
    # Real-time (market hours only)
    "vix_structure": {"interval_min": 15, "market_hours_only": True},
    "put_call": {"interval_min": 60, "market_hours_only": True},

    # Hourly
    "fed_futures": {"interval_min": 60, "market_hours_only": True},

    # Daily
    "finviz_screens": {"interval_min": 240, "market_hours_only": False},
    "earnings_calendar": {"interval_min": 360, "market_hours_only": False},

    # Weekly
    "aaii_sentiment": {"interval_min": 10080, "market_hours_only": False},
    "cot_report": {"interval_min": 10080, "market_hours_only": False},

    # Periodic
    "job_postings": {"interval_min": 4320, "market_hours_only": False},  # 3 days
}
```

### Usage

```python
from src.data.sources.collection_daemon import DataCollectionDaemon

# Start daemon
daemon = DataCollectionDaemon()
await daemon.start()

# Or collect everything once
await daemon.collect_all_now()

# Check status
status = await daemon.get_collection_status()
```

---

## Signal Integration

### New Fields in AggregatedSignal

```python
@dataclass
class AggregatedSignal:
    # ... existing fields ...

    # NEW: Market regime signals
    vix_structure_signal: float = 0.0  # -1 to +1
    breadth_signal: float = 0.0

    # NEW: Sentiment extremes
    aaii_signal: float = 0.0  # Contrarian
    cot_signal: float = 0.0  # Follow commercials
    put_call_signal: float = 0.0  # Contrarian at extremes

    # NEW: Short interest
    short_squeeze_score: float = 0.0
```

### Weight Configuration

```python
WEIGHTS = {
    # Existing
    "swing": 0.20,
    "intraday": 0.10,
    "ml": 0.10,
    "congressional": 0.08,
    "insider": 0.08,
    "options_flow": 0.08,
    "sentiment": 0.04,
    "technical": 0.08,

    # NEW
    "vix_structure": 0.05,
    "breadth": 0.05,
    "aaii": 0.03,
    "cot": 0.04,
    "put_call": 0.04,
    "short_interest": 0.03,
}
```

---

## Testing

### Run All Tests

```bash
PYTHONPATH=. python scripts/test_new_data_sources.py
```

### Test Individual Source

```python
from src.data.sources.alternative.vix_structure import VIXStructureSource

source = VIXStructureSource()
structure = await source.get_structure()
print(f"VIX slope: {structure.slope}")
print(f"Signal: {structure.mean_reversion_signal}")
```

### Verify Cached Data

```bash
ls -la ~/quant_results/live/data_cache/
cat ~/quant_results/live/data_cache/vix_structure.json | jq
```

---

## Verification Checklist

- [x] All 17 source files created and tested
- [x] Collection daemon orchestrates correctly
- [x] All cached files have timestamps
- [x] to_dict() and from_dict() serialization works
- [x] Signal values in expected -1 to +1 range
- [x] Rate limiting respects source limits
- [x] Market hours awareness works correctly
- [x] Graceful failure on network errors

---

## Future Enhancements

1. **Historical Data Backfill**: Scrape historical data for backtesting
2. **Alert Integration**: Alert on extreme readings (AAII >55% bullish, etc.)
3. **Composite Regime Score**: Combine VIX + breadth + put/call into single regime score
4. **Thesis Auto-Linking**: Automatically link events (FDA, earnings) to theses
5. **Source Reliability Tracking**: Track source uptime and accuracy

---

*Created: 2026-01-10*
*Purpose: Document free data source implementation for future reference and maintenance*
