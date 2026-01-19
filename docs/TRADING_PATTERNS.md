# Trading Patterns & Meta-Learnings

**Purpose**: Accumulated wisdom from trading experience. This file is referenced by `/thesis`, `/morning-briefing`, and the brainstorm-agent to ensure patterns are applied consistently.

**Last Updated**: 2026-01-19

---

## Pattern 1: Vehicle Enumeration

**Learned From**: Memory thesis - positioned MU but missed WDC/STX/SNDK (+200-500%)

### The Pattern
When identifying a thesis, enumerate ALL beneficiaries across the value chain, not just the obvious plays.

### Checklist
When creating ANY thesis, complete this checklist:

- [ ] **Direct Beneficiaries**: Companies doing the primary work
- [ ] **Suppliers**: Who supplies the direct beneficiaries?
- [ ] **Customers**: Who benefits from cheaper/better output?
- [ ] **ETFs**: Sector/thematic ETFs that capture the trend
- [ ] **Adjacent Sectors**: What related industries benefit?
- [ ] **Options Plays**: Leveraged exposure via calls/LEAPs
- [ ] **International**: Non-US companies in the same space
- [ ] **Losers**: Who loses if the thesis plays out? (short candidates)

### Example: "AI Needs Storage" Thesis
- Direct: NVDA, AMD (chips)
- Suppliers: AMAT, LRCX, KLAC (equipment)
- Storage (MISSED): WDC, STX, SNDK (HDD/SSD for data centers)
- Memory: MU, SK Hynix (HBM)
- ETFs: SMH, SOXX
- Infrastructure: EQIX, DLR (data centers)
- Power: VST, CEG (electricity)

---

## Pattern 2: Converging Signals

**Learned From**: HOOD rally - multiple independent signals pointed same direction

### The Pattern
High-confidence trades occur when 3+ independent signal types converge. Don't act on single signals.

### Signal Categories
1. **Technical**: Price action, momentum, support/resistance
2. **Fundamental**: Earnings, valuation, growth
3. **Alternative Data**: Congressional trades, insider buying, options flow
4. **Sentiment**: Social mentions, analyst ratings, news tone
5. **Macro**: Fed policy, sector rotation, regime

### Convergence Scoring
| Signals Aligned | Confidence | Position Size |
|-----------------|------------|---------------|
| 5/5 | Very High | 10-15% |
| 4/5 | High | 7-10% |
| 3/5 | Moderate | 5-7% |
| 2/5 | Low | 2-5% or skip |
| 1/5 | None | Do not trade |

### Example: HOOD in 2025
- Technical: Breaking out of base
- Fundamental: Crypto revenues +300%
- Alternative: App rankings improving
- Sentiment: Reddit bullish, retail returning
- Macro: Crypto bull market, S&P 500 inclusion
- **Result**: 5/5 convergence → 185% gain

---

## Pattern 3: Use Existing Data Sources

**Learned From**: Analysis showed 32+ data sources implemented but unused

### The Pattern
The biggest alpha isn't from NEW data - it's from USING data we already have.

### Morning Briefing Data Check
For EVERY morning briefing, explicitly check:

| Source | File | Check For |
|--------|------|-----------|
| Weather | `weather.py` | HDD anomalies → nat gas |
| FDA Calendar | `fda_calendar.py` | Upcoming PDUFA dates |
| Short Interest | `short_interest.py` | Squeeze candidates |
| Reddit | `reddit.py` | Mention spikes |
| Options Flow | `options_flow.py` | Unusual activity |
| Congressional | `congressional_trades.py` | Cluster buying |
| Insider | `insider.py` | Form 4 clusters |
| Job Postings | `job_postings.py` | Hiring changes |

### Thesis Formation Data Check
When creating a thesis, check if we have relevant data:
- Does our alt-data support/contradict?
- What would change our conviction?
- What data should we monitor?

---

## Pattern 4: Squeeze Mechanics

**Learned From**: KSS +90% in one day on short squeeze

### The Pattern
High short interest + rising social mentions = squeeze potential. This is MECHANICAL, not fundamental.

### Squeeze Screening Criteria
```
Short Interest > 30% of float
AND Social Mentions 7d Growth > 100%
AND Market Cap < $10B (small enough to move)
AND Cheap OTM Calls Available
```

### Action
- Small position (2-5%) via calls
- Asymmetric risk/reward
- Don't hold for fundamentals - exit on squeeze

---

## Pattern 5: Binary Event Positioning

**Learned From**: CAPR +535% on Phase 3 data, missed despite having FDA calendar

### The Pattern
Binary events (FDA, earnings, trials) have known dates. Position BEFORE, not after.

### Event Calendar Check
Weekly, review:
- FDA PDUFA dates (next 30 days)
- Major earnings (next 7 days)
- Fed meetings (next 14 days)
- Economic data releases

### Positioning Rules
- 2-3 weeks before binary event
- Use options for limited risk
- Size based on probability assessment
- Accept that some will be total losses

---

## Pattern 6: Weather → Commodity Trades

**Learned From**: Nat gas +140% on Dec 2025 cold snap, we had the data

### The Pattern
Weather anomalies predict commodity moves. We have the data in `weather.py`.

### Correlations
| Weather Event | Trade |
|---------------|-------|
| HDD > 2 std dev | Long UNG/nat gas |
| CDD > 2 std dev | Long utilities, short nat gas |
| Drought in ag regions | Long DBA, short crop-dependent |
| Hurricane season active | Long refiners (short-term) |

### Implementation
Monitor HDD/CDD anomalies weekly during heating/cooling seasons.

---

## Pattern 7: Policy → Behavior → Stock

**Learned From**: Tariff fears → Chinese app downloads surge → CTS International +10%

### The Pattern
Policy changes trigger consumer behavior changes that show up in app data before stock moves.

### Chain of Causation
```
Policy Event (tariffs, bans, regulations)
    ↓
Consumer Behavior Change (hoarding, switching, avoiding)
    ↓
App Usage Data (rankings, downloads, engagement)
    ↓
Stock Price Movement
```

### Data to Monitor
- App rankings during policy uncertainty
- Google Trends for behavior shifts
- Social sentiment for consumer reactions

---

## Pattern 8: Derivative Plays

**Learned From**: Crypto rally → HOOD benefits without holding crypto directly

### The Pattern
Some stocks are derivatives of macro trends without direct exposure. These often have better risk/reward.

### Examples
| Trend | Direct Exposure | Derivative Play |
|-------|-----------------|-----------------|
| Crypto rally | BTC, ETH | HOOD, COIN, MSTR |
| AI boom | NVDA | SMH, VST, WDC |
| EV adoption | TSLA | ALB, PCAR |
| Rate cuts | TLT | XLF, XLRE |

### Why Derivatives Can Be Better
- Less crowded
- Better liquidity
- Multiple revenue streams (hedge)
- Often cheaper valuation

---

## Pattern 9: Social Spike Detection

**Learned From**: DNUT +90% pre-market, Stocktwits caught it hours early (we don't monitor Stocktwits)

### The Pattern
Social mention spikes precede price moves. The earlier the detection, the better the entry.

### Current Gaps
- We monitor Reddit but not Stocktwits
- No alerting on spike detection
- Not integrated into morning briefing

### Ideal Detection
```
IF social_mentions_6h > 3x average
AND market_cap < $5B
AND volume_pre_market > 2x average
THEN alert for potential move
```

---

## Pattern 10: Position Sizing Discipline

**Learned From**: Venezuela thesis - concentrated in SLB/XLE, missed tanker outperformance

### The Pattern (From CLAUDE.md)
High conviction ≠ high concentration. Start equal weight, let winners prove themselves.

### Rules
1. **New thesis**: Equal weight across ALL vehicles
2. **Let winners emerge**: Only concentrate AFTER 10%+ outperformance
3. **Separate timing**: Immediate vs future beneficiaries may have different timing
4. **Max single position**: 15% (reduced from 20%)
5. **Max single thesis**: 35%

---

## How to Use This Document

### For /thesis Skill
Before finalizing any thesis:
1. Run Vehicle Enumeration Checklist (Pattern 1)
2. Check for Converging Signals (Pattern 2)
3. Identify which data sources to monitor (Pattern 3)
4. Assess if there are derivative plays (Pattern 8)

### For /morning-briefing Skill
Every morning:
1. Check all data sources in Pattern 3 table
2. Look for signal convergence (Pattern 2)
3. Review weather anomalies (Pattern 6)
4. Check for social spikes (Pattern 9)
5. Review upcoming binary events (Pattern 5)

### For brainstorm-agent
When generating ideas:
1. Consider squeeze candidates (Pattern 4)
2. Look for policy → behavior chains (Pattern 7)
3. Identify derivative plays (Pattern 8)
4. Check unused data sources (Pattern 3)

---

## Adding New Patterns

When a significant learning emerges from trading:

1. Add it to this file with:
   - **Learned From**: The specific trade/situation
   - **The Pattern**: Clear statement of the insight
   - **Checklist/Rules**: Actionable steps
   - **Example**: Concrete illustration

2. Update the "How to Use" section if the pattern affects workflow

3. Consider if it should also go in CLAUDE.md (only if it's a CRITICAL rule)
