# Alternative Data Opportunities Analysis

**Created**: 2026-01-19
**Purpose**: Identify missed opportunities and improve alternative data usage
**Status**: Future Plans / Discussion

---

## Overview

This document analyzes opportunities we missed and how our existing alternative data sources could have caught them. We take two complementary approaches:

1. **Empirical-First**: Start with actual stock moves from the last few months, then reverse-engineer what data could have predicted them
2. **Hypothesis-First**: Start with our data sources and identify untapped alpha potential

---

## Part 1: Empirical Analysis (Stock Moves → Data Signals)

### Recent Major Movers (Q4 2025 - Jan 2026)

| Stock | Move | Timeframe | What Happened |
|-------|------|-----------|---------------|
| CAPR | +535% | Dec 3, 2025 | Phase 3 DMD trial success |
| WVE | +147% | Dec 2025 | Phase 1 obesity trial data |
| RADX | +150% | Dec 2025 | Brain metastases trial endpoint |
| HOOD | +185% YTD | 2025 | Crypto boom, S&P 500 inclusion |
| KSS | +90% 1-day | Jun 2025 | Short squeeze (50% short interest) |
| DNUT | +90% pre-market | 2025 | Stocktwits mentions spike 500% |
| WDC/STX | +275%/+226% | 2025 | AI storage demand (memory thesis) |

### Deep Dive: Could We Have Caught These?

#### 1. Capricor (CAPR) +535% - Biotech Binary Event

**What Happened**:
- Dec 3, 2025: Phase 3 HOPE-3 trial showed 54% slowing of DMD progression
- Stock went from ~$6 to ~$38 in one day

**Leading Indicators Available**:
- **FDA Calendar** (`fda_calendar.py`): PDUFA dates and trial readouts are scheduled. We had this data source but weren't tracking CAPR.
- **September 2025 Signal**: FDA agreed HOPE-3 could serve as the "additional study" - this was a major de-risking event
- **Options Flow**: Pre-announcement call buying likely spiked (we have `options_flow.py`)
- **Insider Activity**: Check for purchases in Oct-Nov 2025

**Could We Have Caught It?**
- **Partially Yes**: FDA calendar would have flagged the binary event
- **What We Missed**: Not scanning small-cap biotechs with upcoming catalysts
- **Enhancement**: Create biotech catalyst scanner combining FDA calendar + options flow + insider buying

---

#### 2. Robinhood (HOOD) +185% - Fundamental Transformation

**What Happened**:
- Crypto trading revenues up 300%+ YoY
- S&P 500 inclusion (Sept 2025) brought passive flows
- Q3 revenue $1.27B, up 100% YoY

**Leading Indicators Available**:
- **App Rankings** (`app_rankings.py`): Robinhood app download/engagement trends
- **Crypto Sentiment**: Bitcoin price as leading indicator for HOOD
- **Social Sentiment** (`reddit.py`): r/wallstreetbets activity on HOOD
- **Google Trends** (`google_trends.py`): Search interest in "Robinhood"

**Could We Have Caught It?**
- **Yes**: Multiple signals converged:
  - Crypto bull market → HOOD revenue driver
  - App ranking improvements → user growth
  - Social sentiment → retail enthusiasm returning
- **What We Missed**: Not connecting crypto price action to HOOD as a derivative play
- **Enhancement**: Create "crypto beta" screen for stocks that benefit from crypto rallies without holding crypto directly (HOOD, COIN, MSTR)

---

#### 3. Kohl's (KSS) +90% Single Day - Short Squeeze

**What Happened**:
- 50% short interest
- Terrible fundamentals (CEO fired, bad earnings)
- Reddit threads went viral → squeeze

**Leading Indicators Available**:
- **Short Interest** (`short_interest.py`): We track this but weren't using it for squeeze candidates
- **Reddit Sentiment** (`reddit.py`): Mentions spike before squeeze
- **Options Flow**: Cheap OTM calls being accumulated

**Could We Have Caught It?**
- **Yes, mechanically**: High short interest + rising social mentions = squeeze risk
- **What We Missed**: Treating short squeeze as a mechanical setup, not fundamental analysis
- **Enhancement**: Create squeeze scanner: `short_float > 30%` AND `social_mentions_growth_7d > 100%`

---

#### 4. Krispy Kreme (DNUT) +90% Pre-Market

**What Happened**:
- 500% spike in Stocktwits mentions detected hours before move
- Stock gapped up 90% pre-market

**Leading Indicators Available**:
- **Social Sentiment**: We only have Reddit (`reddit.py`), not Stocktwits
- **Unusual Options Activity**: Likely showed up in options flow

**Could We Have Caught It?**
- **No with current tools**: We don't monitor Stocktwits
- **Enhancement**: Add Stocktwits monitoring to `social_sentiment.py`
- **Alert**: Flag when social mentions spike >300% in <6 hours on low-volume names

---

#### 5. Data Storage Stocks (WDC, STX, SNDK) +200-500%

**What Happened**:
- AI infrastructure build-out required massive storage
- "Nearline" HDD market saw largest price increases in history
- We had the Memory/HBM thesis but didn't extend to traditional storage

**Leading Indicators Available**:
- **Our Memory Thesis**: We were positioned in MU (memory) but missed WDC/STX
- **Earnings Revisions**: Analyst estimates were being raised
- **Job Postings** (`job_postings.py`): Hiring activity at storage companies
- **Patent Filings** (`patent_filings.py`): R&D activity in storage tech

**Could We Have Caught It?**
- **Should Have**: We had the thesis (AI needs storage), we just applied it too narrowly
- **What We Missed**: Memory ≠ just DRAM/HBM. Traditional HDDs benefit from AI cold storage
- **Enhancement**: Broaden thesis vehicles - when identifying a theme, enumerate ALL beneficiaries across the value chain

---

### Natural Gas Weather Play (Dec 2025)

**What Happened**:
- Nat gas spiked from $2.20 (2024) to $5.29 in early Dec 2025 (+140%)
- December temps 23.9% colder than normal
- West South Central region 46.2% below normal

**Leading Indicators Available**:
- **Weather Data** (`weather.py`): We compute Heating Degree Days (HDD)
- **Historical correlation**: HDD anomalies → natural gas prices

**Could We Have Caught It?**
- **Yes**: Weather data was available 1-2 weeks before price spike
- **What We Missed**: Not connecting weather signals to energy positions
- **Enhancement**: Create HDD anomaly alert → UNG/nat gas position sizing

---

## Part 2: Hypothesis-First Analysis (Data Sources → Potential Alpha)

### Currently Implemented Data Sources (32+)

| Category | Sources | Status |
|----------|---------|--------|
| **Market Structure** | VIX term structure, Put/call ratios, Short interest | Implemented, partially used |
| **Social/Sentiment** | Reddit, AAII survey, Newsletter sentiment | Implemented, underused |
| **Economic** | Fed futures, Treasury calendar, Economic releases | Implemented, rarely used |
| **Events** | FDA calendar, IPO calendar, Earnings calendar | Implemented, never used |
| **Alternative** | Congressional trades, Insider trading, Options flow | Implemented, actively used |
| **Innovation** | Patents, Job postings, App rankings, GitHub activity | Implemented, never used |
| **Weather** | Temperature, precipitation, HDD/CDD | Implemented, never used |

### High-Potential Unused Sources

#### 1. Weather → Energy/Agriculture Trades

**Our Data**: `weather.py` computes HDD, CDD, GDD for 15+ locations including agricultural regions.

**Untapped Alpha**:
- HDD anomalies → Natural gas (UNG), heating oil
- CDD anomalies → Electricity demand, utilities
- GDD anomalies → Crop yields, agricultural commodities
- Extreme weather → Retail foot traffic shifts (online vs physical)

**Implementation**:
```python
# Alert when cumulative HDD > 2 std dev above 30-day rolling mean
weather_signal = WeatherFeatureEngine.compute_weather_anomaly(hdd_series, window=30)
if weather_signal.iloc[-1] > 2.0:
    alert("Consider UNG long position - extreme cold")
```

---

#### 2. App Rankings → Consumer Stock Signals

**Our Data**: `app_rankings.py` tracks iOS/Android rankings for public company apps.

**Untapped Alpha**:
- App ranking surge → Leading indicator for quarterly user growth
- DHgate/Taobao surge in April 2025 → Predicted Chinese e-commerce plays
- Cash App ranking → SQ revenue indicator
- Gaming app spikes → TTWO, EA, RBLX

**Missing Coverage**:
- Chinese e-commerce apps (DHgate, Taobao, Temu, Shein)
- Fintech apps (Chime, Current, etc.)
- Gaming apps

**Implementation**:
```python
# Add to APP_COMPANY_MAP
"DHgate": "DHGate logistics partners",  # CTS International
"Taobao": "BABA",
"Temu": "PDD",
```

---

#### 3. Job Postings → Company Health Indicator

**Our Data**: `job_postings.py` tracks hiring activity with department breakdowns.

**Untapped Alpha**:
- Hiring surge → Growth acceleration (bullish)
- Hiring freeze → Cost cuts coming, possible layoffs (bearish)
- Engineering-heavy hiring → Product investment (long-term bullish)
- Sales-heavy hiring → Revenue push, possibly desperation

**Example Signal**:
- META posted -40% engineering roles before 2023 layoffs
- Signal was visible 30-60 days before announcement

**Implementation**:
- Automate weekly scraping of top 100 company career pages
- Alert when `change_pct_30d < -20%` for engineering roles

---

#### 4. FDA Calendar → Biotech Binary Events

**Our Data**: `fda_calendar.py` tracks PDUFA dates.

**Untapped Alpha**:
- PDUFA dates are known months in advance
- Stocks move 50-200%+ on approvals
- Can position in calls 2-3 weeks before binary events
- Combine with options flow for smarter positioning

**Implementation**:
- Generate weekly report of upcoming PDUFA dates
- Cross-reference with options flow for unusual activity
- Flag catalyst + high IV rank opportunities

---

#### 5. Short Interest + Social = Squeeze Scanner

**Our Data**: `short_interest.py` + `reddit.py`

**Untapped Alpha**:
- High short interest alone isn't a signal (can stay short a long time)
- High short interest + rising social mentions = potential squeeze
- KSS, GME, AMC all showed this pattern

**Implementation**:
```python
SQUEEZE_CANDIDATES = [
    stock for stock in universe
    if short_interest[stock] > 0.30  # >30% short
    and social_mentions_growth_7d[stock] > 1.0  # >100% growth
    and market_cap[stock] < 10e9  # Small enough to squeeze
]
```

---

#### 6. GitHub Activity → Developer Tools

**Our Data**: `github_activity.py` tracks repo stars, commits, contributors.

**Untapped Alpha**:
- Open source adoption leads enterprise revenue by 2-3 quarters
- MongoDB, Elastic, Datadog all had star growth before stock moves
- Track: Prisma, Supabase, Drizzle (database tools), LangChain (AI)

**Implementation**:
- Map key open source repos to parent companies
- Alert when weekly star growth > 2x average
- Cross-reference with job postings (hiring to support growth)

---

#### 7. Patent Filings → Innovation Signals

**Our Data**: `patent_filings.py` tracks USPTO filings by company.

**Untapped Alpha**:
- Patent surge in new area = strategic pivot
- Patent surge in existing area = defending/expanding moat
- Patent decline = R&D cutbacks

**Implementation**:
- Track patent filings by category/technology
- Alert when filings in new category exceed 20% of total
- Compare to peers in same industry

---

## Part 3: Implementation Priorities

### Tier 1: Low Effort, High Potential

| Enhancement | Effort | Expected Alpha |
|-------------|--------|----------------|
| Weather → UNG correlation alerts | 1 day | High (weather is free, signal is clear) |
| Squeeze scanner (short + social) | 1 day | Very High (asymmetric payoffs) |
| Crypto-beta screen (HOOD, COIN, MSTR) | 2 hours | Medium (simple to implement) |
| Broaden thesis vehicles automatically | Design change | High (catches adjacent plays) |

### Tier 2: Medium Effort, High Potential

| Enhancement | Effort | Expected Alpha |
|-------------|--------|----------------|
| FDA calendar weekly report | 1 day | High (binary events known in advance) |
| Add Stocktwits to social monitoring | 2-3 days | High (caught DNUT signal) |
| Automate job posting scraper | 3-5 days | Medium (30-60 day lead time) |
| Chinese e-commerce app tracking | 1 day | Medium (event-driven) |

### Tier 3: Higher Effort

| Enhancement | Effort | Expected Alpha |
|-------------|--------|----------------|
| GitHub → company mapping pipeline | 1 week | Medium (long lead time) |
| Patent filing analysis pipeline | 1 week | Low-Medium (signal is slow) |
| App ranking automated scraping | 3-5 days | Medium (consumer stocks only) |

---

## Part 4: Meta-Learnings

### Why We Missed Opportunities

1. **Built but didn't use**: We have 32+ data sources implemented, but many have never generated a trade signal
2. **Too narrow on thesis vehicles**: Memory thesis was correct, but we only bought MU, not WDC/STX/SNDK
3. **Didn't connect dots**: Weather data exists, but we never linked it to energy positions
4. **Missing key platforms**: No Stocktwits monitoring despite it catching DNUT signal hours early
5. **No systematic catalyst calendar**: FDA dates are public but we weren't tracking them

### Key Principle: Use What We Have

The biggest alpha isn't from finding NEW data sources - it's from actually USING the 32+ sources we already built.

**Action Items**:
1. Audit each data source in `src/data/sources/alternative/`
2. For each: Is it being collected? Is it generating signals? Is it influencing decisions?
3. Create cron jobs to populate data
4. Create alerts for actionable signals
5. Integrate into morning briefing and thesis formation

---

## References

**2025 Market Analysis**:
- [Yahoo Finance - Market Winners/Losers 2025](https://finance.yahoo.com/news/stocks-market-biggest-winners-losers-110007084.html)
- [Investing.com - Sector-by-Sector Review](https://www.investing.com/analysis/winners-and-losers-of-2025-a-sectorbysector-stock-market-review-200672786)
- [StockTitan - 2025 Year-End Analysis](https://www.stocktitan.net/articles/stock-market-2025-year-end-comprehensive-analysis)

**Natural Gas/Weather**:
- [S&P Global - Cold Snap Impact](https://www.spglobal.com/energy/en/news-research/latest-news/natural-gas/120925-cold-snap-boosts-us-eias-spot-gas-price-outlook-for-late-2025-early-2026)
- [EIA - Natural Gas Outlook](https://www.eia.gov/outlooks/steo/report/natgas.php)

**Biotech Catalysts**:
- [Capricor HOPE-3 Results](https://www.capricor.com/investors/news-events/press-releases/detail/331/capricor-therapeutics-announces-positive-topline-results)
- [FinancialContent - CAPR Analysis](https://markets.financialcontent.com/stocks/article/marketminute-2025-12-3-capricor-therapeutics-nasdaq-capr-soars-535-to-eight-year-high-on-landmark-duchenne-muscular-dystrophy-treatment-results)

**Meme Stocks/Social**:
- [Medium - Reddit Stock Analysis](https://medium.com/@tzjy/from-meme-mania-to-market-signals-what-reddits-hottest-stock-picks-tell-us-about-the-market-in-b4d0024031cd)
- [AInvest - Meme Stock Revolution](https://www.ainvest.com/news/2025-meme-stock-revolution-ai-retail-sentiment-reshaping-speculative-investing-2508/)

**Robinhood/Crypto**:
- [Yahoo Finance - HOOD Rally Analysis](https://finance.yahoo.com/news/why-did-robinhood-rally-220-143056495.html)
- [Stocktwits - HOOD Assets Top $300B](https://stocktwits.com/news-articles/markets/equity/why-did-robinhood-stock-rise-in-after-hours-trading/chw8Qz8Rdw9)

**App Rankings**:
- [Global Times - Chinese Apps Dominate US](https://www.globaltimes.cn/page/202504/1332249.shtml)
