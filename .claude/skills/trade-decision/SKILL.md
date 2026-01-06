---
name: trade-decision
description: Make trading decisions based on signals, research, and latent market knowledge. Consumes morning briefing and statistical signals, outputs BUY/SELL/HOLD decisions with detailed reasoning. Run after /morning-briefing.
allowed-tools: Read, Bash(PYTHONPATH=*), Bash(curl:*), Glob, Grep, Write, WebSearch
---

# Trade Decision Skill

LLM-powered trading decision engine that synthesizes research, signals, and market knowledge.

## Purpose

This skill makes final trading decisions by:
1. **Consuming** morning briefing + statistical signals
2. **Applying** latent knowledge about markets, sectors, companies
3. **Outputting** BUY/SELL/HOLD decisions with reasoning
4. **Logging** all decisions for feedback loop

## Prerequisites

Run `/morning-briefing` first to generate today's research context.

## Quick Start

```bash
# Generate decisions (after morning briefing)
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.decision.decision_logger import DecisionLogger
logger = DecisionLogger()
decisions = logger.get_today_decisions()
print(f"Decisions today: {len(decisions)}")
for d in decisions:
    print(f"  {d.action.value} {d.symbol} ({d.confidence:.0%} confidence)")
EOF
```

## Decision Framework

When making trading decisions, I (Claude) should systematically consider:

### 1. Statistical Signal Quality
- What is the signal confidence?
- How many confirming indicators?
- Historical performance of this signal type?

### 2. Research Context (from briefing)
- Any overnight news affecting this symbol?
- Prediction market shifts relevant?
- Congressional trading signals?

### 3. Latent Market Knowledge

For each symbol, explicitly consider:

**Company-Specific:**
- Business model and competitive moat
- Recent earnings quality and guidance
- Management track record and credibility
- Key customers, suppliers, and dependencies
- Regulatory exposure and risks

**Sector Dynamics:**
- Where in the sector cycle (early/mid/late)?
- Key sector catalysts or headwinds?
- Relative valuations within sector?
- Cross-sector correlations?

**Macro Context:**
- Fed policy implications?
- Economic cycle position?
- Geopolitical risks?
- Seasonal patterns (January effect, summer doldrums, etc.)?

**Behavioral Factors:**
- Current sentiment extremes?
- Crowded trades (everyone on same side)?
- Retail vs institutional positioning?
- Options market signals (put/call, skew)?

### 4. Portfolio Context
- Current exposure to this symbol/sector?
- Correlation with existing positions?
- Risk capacity remaining?
- PDT constraints (if <$25k account)?

### 5. Risk Assessment
- What could go wrong?
- What's the max loss scenario?
- How liquid is exit if thesis fails?

## Decision Output Format

For each decision, log:

```python
from src.decision.decision_logger import create_decision, Action, DecisionLogger

decision = create_decision(
    symbol="SLB",
    action=Action.BUY,
    confidence=0.75,
    size_pct=10.0,  # % of portfolio
    reasoning="""
    Venezuela reconstruction thesis confirmed by overnight State Dept comments.
    SLB has 15 rigs already in-country, first-mover advantage.
    Pre-market showing strength (+1.2%).
    Options flow showing institutional accumulation.

    Latent knowledge: SLB is the dominant oilfield services player with
    proven ability to ramp operations quickly. Management has navigated
    sanctions before. Their Middle East operations provide template for
    Venezuela ramp.
    """,
    key_factors=[
        "Venezuela contract announcements imminent",
        "Pre-market strength confirming thesis",
        "Institutional options flow bullish",
        "First-mover advantage with stored equipment",
    ],
    risks=[
        "Geopolitical reversal (US policy change)",
        "Oil price collapse",
        "Operational delays in Venezuela",
        "Sector rotation away from energy",
    ],
    context={
        "briefing_date": "2026-01-06",
        "market_sentiment": "bullish",
        "sp500_futures": "+0.3%",
        "sector_performance": "energy +1.5%",
    },
    stop_loss_pct=15.0,
    take_profit_pct=30.0,
    expected_hold_days=10,
)

# Log the decision
logger = DecisionLogger()
logger.log_decision(decision)
```

## Decision Rules

### Position Sizing
| Confidence | Size (% of portfolio) |
|------------|----------------------|
| 90%+ | 20% max |
| 75-90% | 15% max |
| 60-75% | 10% max |
| <60% | 5% max or HOLD |

### Stop Loss Guidelines
| Type | Stop Loss |
|------|-----------|
| High conviction thesis | -15% |
| Moderate conviction | -10% |
| Speculative | -5% |
| Day trade | -3% |

### When to HOLD (No Action)
- Confidence <50%
- Signal + context misalignment
- Already at max sector exposure
- Unclear risk/reward
- PDT constraint would be triggered

### When to BUY
- Statistical signal + research alignment
- Clear thesis with defined exit
- Acceptable risk/reward (2:1 minimum)
- Portfolio has capacity

### When to SELL/CLOSE
- Thesis invalidated
- Stop loss triggered
- Take profit target reached
- Better opportunity elsewhere
- Risk management (reduce exposure)

## Example Session

```
User: /trade-decision

Claude: I'll analyze today's signals against the morning briefing and make trading decisions.

## Context Review

**Morning Briefing Summary:**
- Market Sentiment: Bullish
- S&P Futures: +0.3%
- Key News: Venezuela stability improving, Fed patient on rates
- Focus Areas: Energy thesis, Options expiring Friday

**Current Portfolio:**
- Total Equity: $95,888
- Energy exposure: 45% (high)
- Cash available: ~$10,000

**Statistical Signals Today:**
1. SLB: BUY signal (bollinger_reversal, strength 0.72)
2. HAL: BUY signal (insider_technical, strength 0.65)
3. VLO: HOLD (no signal)

---

## Trading Decisions

### Decision 1: SLB - HOLD (despite BUY signal)

**Reasoning:**
Although SLB has a BUY signal, I'm recommending HOLD because:
1. Already have significant SLB exposure (16% of portfolio)
2. Energy sector at 45% - adding more increases concentration risk
3. The thesis is playing out as expected - no need to add aggressively

**Latent Knowledge Applied:**
- SLB typically moves with oil prices in short term
- Reconstruction contracts are multi-year - no urgency to add
- Sector rotation could hurt short-term even if thesis correct

**Action:** HOLD
**Confidence:** 65% (in HOLD decision)

---

### Decision 2: HAL - SMALL ADD

**Reasoning:**
HAL has insider_technical signal and is our second-highest conviction name.
Adding a small position to maintain exposure without over-concentrating.

**Latent Knowledge Applied:**
- HAL benefits from same Venezuela thesis as SLB
- Slightly smaller player = more upside if thesis plays out
- Options liquidity lower than SLB - prefer stock

**Action:** BUY
**Size:** 3% of portfolio (~$2,900)
**Entry:** Market order at open
**Stop Loss:** -10%
**Take Profit:** +25%
**Expected Hold:** 10 days
**Confidence:** 68%

---

### Decision 3: Review Feb Options

**Reasoning:**
Options expiring Feb 6 need attention. Based on current prices:
- VLO calls: Down 16%, thesis slow - consider closing
- GLD calls: Down 5%, gold thesis unclear - monitor

**Action:** FLAG FOR REVIEW
**Note:** Check mid-session prices before deciding

---

## Decisions Logged

1. HAL BUY - Decision ID: abc123
2. VLO review flagged
3. GLD review flagged

Run /execute-trades to execute the HAL decision.
```

## Integration

### Input (from morning-briefing)
```python
# Load today's briefing
from src.decision.morning_briefing import MorningBriefingGenerator
briefing = MorningBriefingGenerator.get_latest_briefing()
```

### Output (to execute-trades)
```python
# Decisions are saved to:
# /home/nock/quant_results/decisions/decisions_YYYY-MM-DD.json

# Execute-trades skill reads pending decisions:
from src.decision.decision_logger import DecisionLogger
logger = DecisionLogger()
pending = logger.get_pending_decisions()
```

## Key Files

| File | Purpose |
|------|---------|
| `/home/nock/quant_results/briefings/` | Morning briefing input |
| `/home/nock/quant_results/decisions/` | Decision logs output |
| `/home/nock/quant_results/TRADING_RULES.md` | Trading rules to follow |
| `/home/nock/quant_results/trading_logs/` | Historical session logs |
