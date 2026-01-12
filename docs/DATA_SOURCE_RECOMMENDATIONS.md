# Data Source Recommendations for ML Pipeline

Based on latent knowledge validation and feature importance analysis, this document provides prioritized recommendations for new data sources to enhance the ML pipeline.

---

## Executive Summary

| Priority | Category | Expected IC | Implementation Effort |
|----------|----------|-------------|----------------------|
| P0 (Critical) | Credit Spreads | 0.04+ | Medium |
| P0 (Critical) | Earnings Revisions | 0.05 | Medium |
| P1 (High) | ETF Flow Data | 0.03 | Low |
| P1 (High) | Sector Lead-Lag Data | 0.03 | Low |
| P2 (Medium) | Options Block Flow | 0.025 | High |
| P2 (Medium) | Analyst Estimate History | 0.02 | Medium |
| P3 (Low) | Board Network Graph | 0.02 | High |

---

## P0: Critical Priority (Implement First)

### 1. Credit Default Swap (CDS) / High Yield Spreads

**Hypothesis**: Credit stress leads equity weakness by 1-5 days

**Why**:
- Credit markets are more institutional, often react faster than equity
- HY spreads spike before equity selloffs
- Validated pattern: credit leads equity in 60%+ of major drawdowns

**Data Sources**:
- **FRED**: ICE BofA High Yield Index (free)
- **Quandl**: CDS spreads by issuer (subscription)
- **Bloomberg Terminal**: Real-time CDS (expensive)

**Implementation**:
```python
# Free implementation using FRED
credit_features = {
    "hy_spread_level": "HY spread in basis points",
    "hy_spread_change_5d": "5-day change in HY spread",
    "hy_spread_percentile": "Historical percentile (252d)",
    "credit_stress_signal": "Spread > 80th percentile",
}
```

**Expected Features**:
- `credit_spread_percentile`: IC = 0.03-0.04
- `credit_widening_signal`: IC = 0.02-0.03

---

### 2. Earnings Estimate Revisions

**Hypothesis**: Estimate momentum predicts returns better than absolute estimates

**Why**:
- Analyst revision velocity captures changing sentiment
- Pre-announces and whisper numbers drive price action
- Earnings acceleration often persists

**Data Sources**:
- **LSEG Refinitiv**: I/B/E/S estimates (subscription)
- **Bloomberg**: Estimate history (subscription)
- **Zacks**: Revision data (subscription)
- **FactSet**: Consensus estimates (subscription)

**Free Alternative**:
- Scrape quarterly EPS from Yahoo Finance
- Build simple revision momentum from changes

**Implementation**:
```python
estimate_features = {
    "eps_revision_1m": "EPS estimate change last month",
    "eps_revision_velocity": "Acceleration of revisions",
    "revision_breadth": "% of analysts revising up",
    "estimate_surprise_history": "Average beat/miss",
}
```

**Expected Features**:
- `eps_revision_momentum`: IC = 0.04-0.05
- `revision_breadth`: IC = 0.03

---

## P1: High Priority

### 3. ETF Flow Data

**Hypothesis**: Large ETF flows predict sector returns

**Why**:
- Massive passive flows move prices
- Creation/redemption units signal demand
- Sector rotation visible in ETF flows

**Data Sources**:
- **ETF.com**: Weekly flows (free)
- **Bloomberg**: Daily flows (subscription)
- **ICI (Investment Company Institute)**: Weekly fund flows (free)

**Free Implementation**:
```python
# Estimate flows from price/volume data
etf_features = {
    "sector_flow_proxy": "Inferred from volume",
    "flow_momentum_10d": "Flow direction momentum",
    "relative_flow_vs_spy": "Sector vs market flow",
}
```

**Expected Features**:
- `sector_flow_proxy`: IC = 0.02-0.03
- `flow_momentum`: IC = 0.02

---

### 4. Sector Lead-Lag Cross-Reference Data

**Hypothesis**: Semiconductors lead tech, banks lead rates, etc.

**Why**:
- Already partially validated in latent knowledge testing
- Need benchmark data for cleaner signals
- Cross-asset relationships are stable

**Data Sources**:
- **Yahoo Finance**: Sector ETF prices (free)
- **FRED**: Rate data (free)
- **Quandl**: Commodity futures (subscription)

**Implementation**:
```python
# Build lead-lag indicators
lead_lag_features = {
    "smh_vs_xlk_lead": "Semis leading tech by 10d",
    "xlf_vs_tnx_beta": "Financials sensitivity to rates",
    "xle_vs_uso_lead": "Energy stocks vs oil",
    "iyt_industrial_lead": "Transports leading industrials",
}
```

**Expected Features**:
- `sector_lead_signal`: IC = 0.02-0.03
- `lead_lag_divergence`: IC = 0.02

---

## P2: Medium Priority

### 5. Options Block Trade Flow

**Hypothesis**: Large options trades precede news by 1-3 days

**Why**:
- Institutional "smart money" signals
- Unusual activity often precedes events
- Currently have volume data but not block trades

**Data Sources**:
- **CBOE**: Livevol (subscription)
- **Market Chameleon**: Unusual activity (subscription)
- **Unusual Whales**: Social + flow (subscription)
- **TradingView**: Some flow data (free tier limited)

**Free Alternative**:
- Use volume surge detection
- Put/call ratio extremes
- IV percentile spikes

**Expected Features**:
- `unusual_call_signal`: IC = 0.02-0.025
- `smart_money_direction`: IC = 0.02

---

### 6. Analyst Estimate and Rating History

**Hypothesis**: Analyst upgrades cluster and lag reality

**Why**:
- Herding behavior is predictable
- Contrarian signal when all analysts agree
- Upgrade/downgrade momentum persists

**Data Sources**:
- **TipRanks**: Analyst ratings (freemium)
- **Benzinga**: Ratings API (subscription)
- **Marketbeat**: Analyst consensus (scrape)

**Expected Features**:
- `analyst_consensus_extreme`: IC = 0.015-0.02
- `upgrade_momentum`: IC = 0.02

---

## P3: Lower Priority (Future)

### 7. Board Network / Insider Network Graph

**Hypothesis**: Insider network effects amplify signals

**Why**:
- Directors connected to multiple boards
- Insider buying may cluster by network
- Information flows through connections

**Data Sources**:
- **BoardEx**: Director relationships (expensive)
- **SEC Form 4**: Build graph manually (free but labor-intensive)

**Expected Features**:
- `network_centrality_signal`: IC = 0.015
- `connected_insider_buying`: IC = 0.02

---

### 8. Capex and M&A Signal from Earnings Calls

**Hypothesis**: NLP on earnings calls reveals capex intentions

**Why**:
- Forward-looking statements in MD&A
- Capex announcements often buried
- Sentiment analysis of Q&A section

**Data Sources**:
- **SeekingAlpha**: Earnings transcripts (freemium)
- **MotleyFool**: Transcripts (scrape)
- **AlphaSpread**: Parsed transcripts

**Expected Features**:
- `capex_tone_change`: IC = 0.015-0.02
- `ma_speculation_score`: IC = 0.01

---

## Implementation Priority Matrix

```
                HIGH IMPACT
                    │
   Credit Spreads ──┤───── Earnings Revisions
          (P0)      │            (P0)
                    │
  ETF Flows ────────┤───── Sector Lead-Lag
     (P1)           │         (P1)
                    │
Options Flow ───────┤───── Analyst History
    (P2)            │         (P2)
                    │
Board Network ──────┤───── Capex NLP
    (P3)            │         (P3)
                    │
   LOW EFFORT ──────┼────── HIGH EFFORT
```

---

## Quick Wins (Implement This Week)

### 1. FRED High Yield Spread
```python
# Add to data collection daemon
from src.data.sources.alternative.fred import FREDDataSource

fred = FREDDataSource()
hy_spread = fred.get_series("BAMLH0A0HYM2")  # ICE BofA HY Index
```

### 2. Sector ETF Lead-Lag
```python
# Already have price data - just need feature computation
from src.data.feature_engineering.latent_knowledge_features import compute_sector_lead_signal

# Compute for all sector pairs
SECTOR_PAIRS = [
    ("SMH", "XLK"),  # Semis -> Tech
    ("XLF", "TLT"),  # Banks -> Rates (inverse)
    ("IYT", "XLI"),  # Transport -> Industrials
]
```

### 3. EPS Revision Proxy
```python
# Scrape quarterly EPS from Yahoo Finance
# Compute quarter-over-quarter changes
# Track analyst count changes
```

---

## Data Budget Estimate

| Source | Monthly Cost | Data Provided |
|--------|--------------|---------------|
| FRED | Free | HY spreads, economic data |
| Yahoo Finance | Free | Prices, basic fundamentals |
| Quandl | $49-299 | Alternative data |
| TipRanks Premium | $30 | Analyst ratings |
| Unusual Whales | $20 | Options flow |
| **Total Basic** | **~$100/mo** | Core alternative data |

| Advanced Sources | Monthly Cost |
|-----------------|--------------|
| Bloomberg Terminal | $2,000+ |
| Refinitiv Eikon | $1,500+ |
| FactSet | $1,000+ |

**Recommendation**: Start with free sources (FRED, Yahoo) + one subscription ($50-100/mo) for highest-IC features.

---

## Validation Requirements

Before integrating any new data source:

1. **Point-in-Time Accuracy**: Ensure no lookahead bias
2. **IC Testing**: Compute IC over 2+ years history
3. **Regime Analysis**: Test in different market conditions
4. **MCPT Validation**: p < 0.05 for any strategy using the data
5. **Correlation Check**: Ensure not redundant with existing features

---

## Integration Checklist

For each new data source:

- [ ] Data collector implemented in `src/data/sources/`
- [ ] Features computed in `src/data/feature_engineering/`
- [ ] Features registered in `feature_registry.py`
- [ ] Backtest with MCPT validation
- [ ] Add to data collection daemon schedule
- [ ] Document in `docs/FREE_DATA_SOURCES.md`
