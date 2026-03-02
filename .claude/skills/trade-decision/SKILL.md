---
name: trade-decision
description: Make trading decisions based on signals, research, and latent market knowledge. Consumes morning briefing and statistical signals, outputs BUY/SELL/HOLD decisions with detailed reasoning. Run after /morning-briefing.
allowed-tools: Read, Bash(PYTHONPATH=*), Bash(curl:*), Glob, Grep, Write, WebSearch
---

# Trade Decision Skill

LLM-powered trading decision engine that synthesizes research, signals, and market knowledge.

## Purpose

This skill makes final trading decisions by:
1. **Consuming** unified state (market, portfolio, signals, theses)
2. **Applying** latent knowledge about markets, sectors, companies
3. **Running** adversarial analysis to challenge every trade
4. **Linking** decisions to investment theses
5. **Outputting** BUY/SELL/HOLD decisions with reasoning
6. **Logging** all decisions for feedback loop

## Prerequisites

Run `/morning-briefing` first or ensure unified state is fresh.

## Quick Start

### Step 0: Get Decision Context (Intelligence Loop)

**CRITICAL: Run this BEFORE making any trade decision.** Surfaces your track record,
calibration data, and relevant learnings for the symbol.

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.intelligence.context_builder import DecisionContextBuilder

# Build context for the symbol you're considering
builder = DecisionContextBuilder()
ctx = builder.build_context("SLB", setup_type="thesis_driven", thesis_id=None)
print(ctx.summary)
EOF
```

Review this context and factor it into your confidence level. If the calibration
data says you're overconfident by 12%, discount your confidence accordingly.

### Step 1: Load Context

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.synthesis.state import UnifiedState
from src.core.paths import paths
import json

# Load unified state
state = UnifiedState.load(paths.live_state)
if state:
    print("=== MARKET ===")
    print(f"Regime: {state.market.regime}")
    print(f"Trend: {state.market.trend}")

    print("\n=== PORTFOLIO ===")
    print(f"Equity: ${state.portfolio.equity:,.2f}")
    print(f"Cash: ${state.portfolio.cash:,.2f}")

    print("\n=== ACTIVE THESES ===")
    for thesis in state.theses:
        print(f"  {thesis.name}: {thesis.conviction:.0f}%")

    print("\n=== SIGNALS ===")
    for symbol, signal in list(state.watchlist_signals.items())[:5]:
        print(f"  {symbol}: composite={signal.composite_score:.2f}, conf={signal.confidence:.2f}")
EOF
```

### Step 2: Review Knowledge Base

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.knowledge.base import KnowledgeBase
from src.core.paths import paths

kb = KnowledgeBase(paths.knowledge)

# Check if we have knowledge about a symbol
symbol = "SLB"
company = kb.get_company(symbol)
if company:
    print(f"=== {company.symbol} ===")
    print(f"Business: {company.business_model}")
    print(f"Moat: {company.moat}")
    print(f"Best setups: {company.best_setups}")
else:
    print(f"No knowledge for {symbol}")
EOF
```

### Step 3: Run Adversarial Analysis

```bash
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from src.decision.adversary import AdversarialAgent

adversary = AdversarialAgent()

# Challenge a proposed trade
analysis = adversary.challenge(
    symbol="SLB",
    proposed_action="BUY",
    reasoning="Venezuela thesis + pre-market strength",
    confidence=0.75,
    context={
        "sector_exposure": 0.45,
        "regime": "risk-on",
    }
)

print(f"=== ADVERSARIAL ANALYSIS ===")
print(f"Concern Level: {analysis.overall_concern_level}")
print(f"Proceed Recommendation: {analysis.proceed_recommendation}")
print(f"Confidence Adjustment: {analysis.confidence_adjustment:+.0%}")

print("\nTiming Concerns:")
for c in analysis.timing_concerns:
    print(f"  - {c}")

print("\nThesis Weaknesses:")
for w in analysis.thesis_weaknesses:
    print(f"  - {w}")

print(f"\nWorst Case: {analysis.worst_case}")
EOF
```

## Decision Framework

When making trading decisions, I (Claude) should systematically consider:

### 1. Thesis Alignment

**Check active theses:**
- Is this symbol linked to an active thesis?
- What is the current conviction level?
- Have any signposts triggered recently?
- Is the thesis on track or deteriorating?

```python
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
theses = tracker.get_theses_for_symbol("SLB")
```

### 2. Statistical Signal Quality

- What is the signal confidence?
- How many confirming indicators?
- Historical performance of this signal type?
- Does signal agree with thesis direction?

### 3. Knowledge Base Context

```python
from src.knowledge.base import KnowledgeBase

kb = KnowledgeBase(paths.knowledge)
company = kb.get_company(symbol)
sector = kb.get_sector("energy")
```

**Company-Specific:**
- Business model and competitive moat
- Recent earnings quality and guidance
- Management track record
- Best trading setups for this stock

**Sector Dynamics:**
- Where in the sector cycle?
- Key sector catalysts or headwinds?
- Relative valuations?

### 4. Adversarial Challenge

**CRITICAL: Every trade gets challenged.**

```python
from src.decision.adversary import AdversarialAgent

adversary = AdversarialAgent()
analysis = adversary.challenge(symbol, action, reasoning, confidence, context)

# Adjust confidence based on adversarial analysis
adjusted_confidence = confidence + analysis.confidence_adjustment
```

If adversary raises high/critical concerns:
- Reconsider the trade
- Address the concerns explicitly in reasoning
- Reduce position size or pass

### 5. Portfolio Context

- Current exposure to this symbol/sector?
- Correlation with existing positions?
- Risk capacity remaining?
- PDT constraints?

### 6. Pre-Mortem

Before finalizing any BUY decision, write a pre-mortem:

> "It's 30 days later and this trade lost money. What happened?"

This forces you to identify failure modes before entering.

## Decision Output Format

```python
from src.decision.decision_logger import create_decision, Action, DecisionLogger
from src.knowledge.thesis import ThesisTracker
from src.decision.adversary import AdversarialAgent

# 1. Run adversarial analysis
adversary = AdversarialAgent()
analysis = adversary.challenge(
    symbol="SLB",
    proposed_action="BUY",
    reasoning="Venezuela thesis confirmed...",
    confidence=0.75,
    context={...}
)

# 2. Find linked thesis
tracker = ThesisTracker(paths.theses)
theses = tracker.get_theses_for_symbol("SLB")
thesis_id = theses[0].id if theses else None

# 3. Create decision with all context
decision = create_decision(
    symbol="SLB",
    action=Action.BUY,
    confidence=0.70,  # Adjusted after adversary
    size_pct=10.0,
    reasoning="""
    Venezuela reconstruction thesis confirmed by overnight State Dept comments.
    SLB has 15 rigs already in-country, first-mover advantage.

    Latent knowledge: SLB is the dominant oilfield services player with
    proven ability to ramp operations quickly.

    Adversary noted: High sector concentration (45%), potential for
    policy reversal. Reducing position size from 15% to 10%.
    """,
    key_factors=[
        "Venezuela contract announcements imminent",
        "Pre-market strength confirming thesis",
        "First-mover advantage",
    ],
    risks=[
        "Geopolitical reversal (US policy change)",
        "Oil price collapse",
        "Already high energy exposure",
    ],
    context={
        "briefing_date": "2026-01-06",
        "regime": "risk-on",
        "sector_exposure": 0.45,
    },
    stop_loss_pct=10.0,
    take_profit_pct=25.0,
    expected_hold_days=10,
    thesis_id=thesis_id,
    pre_mortem="Policy reversal forces exit at loss; or oil collapse <$60 kills thesis",
    adversarial_notes=f"Concern level: {analysis.overall_concern_level}. " +
                      f"Adjusted confidence: -5%. Key issue: sector concentration.",
)

# 4. Log the decision
logger = DecisionLogger()
logger.log_decision(decision)

# 5. Log signals that influenced this decision (for quality tracking)
from src.monitoring.signal_quality_tracker import log_signal_outcome

# Log each signal type that influenced the trade
log_signal_outcome(
    signal_type="technical",
    symbol="SLB",
    direction="bullish",
    signal_strength=0.72,  # From swing_signal
    acted_on=True,
)

log_signal_outcome(
    signal_type="insider",
    symbol="SLB",
    direction="bullish",
    signal_strength=0.65,
    acted_on=True,
)
```

## Step 7: Log Predictions (Intelligence Loop)

**After every decision, log explicit predictions.** This is what makes the system
get smarter over time.

```python
from src.db.write_api import athena_db

# Log a direction prediction for every BUY/SELL
athena_db.save_prediction({
    "decision_id": decision.id,
    "thesis_id": thesis_id,
    "symbol": "SLB",
    "prediction_type": "direction",  # or price_target, timeframe_move, event_outcome
    "direction": "bullish",          # or bearish
    "confidence": 0.70,              # Your adjusted confidence
    "timeframe_days": 10,            # Expected resolution window
    "reasoning_category": "thesis_driven",  # thesis_driven, technical, geopolitical, etc.
    "setup_type": "thesis_driven",
    "key_reasoning": "Venezuela thesis + pre-market strength. Adversary cleared at medium concern.",
})

# Optional: Log a more specific prediction
athena_db.save_prediction({
    "decision_id": decision.id,
    "symbol": "SLB",
    "prediction_type": "timeframe_move",
    "direction": "bullish",
    "target_value": 5.0,            # Expected +5% move
    "confidence": 0.55,
    "timeframe_days": 20,
    "reasoning_category": "thesis_driven",
    "key_reasoning": "SLB should hit $48 as Venezuela contracts are announced",
})
```

**Prediction types:**
- `direction` — stock goes up/down (most common)
- `price_target` — stock reaches specific price
- `timeframe_move` — stock moves X% within N days
- `event_outcome` — binary event (earnings beat, FDA approval)
- `thesis_validation` — thesis plays out as expected

## Signal Quality Tracking

**IMPORTANT:** Log which signals influenced each decision to track signal quality over time.

### When Making a Trade Decision

```python
from src.monitoring.signal_quality_tracker import log_signal_outcome

# Log ALL signals that influenced the decision
# This builds the dataset for measuring signal quality

# Example: Technical signal led to BUY
log_signal_outcome(
    signal_type="technical",  # Options: technical, insider, congressional, options, squeeze, sentiment, social
    symbol="HAL",
    direction="bullish",      # or "bearish"
    signal_strength=0.72,     # Signal confidence 0-1
    acted_on=True,            # We traded on this signal
)

# Example: Congressional signal we noted but didn't act on
log_signal_outcome(
    signal_type="congressional",
    symbol="NVDA",
    direction="bullish",
    signal_strength=0.60,
    acted_on=False,           # Signal generated but we passed
)
```

### When Closing a Position (in /eod-review)

Update signal outcomes with actual P&L to measure quality:

```python
from src.monitoring.signal_quality_tracker import log_signal_outcome

# When closing HAL position that was opened based on insider signal
log_signal_outcome(
    signal_type="insider",
    symbol="HAL",
    direction="bullish",
    signal_strength=0.65,
    acted_on=True,
    pnl=129.96,              # Actual P&L in dollars
    pnl_pct=4.5,             # Actual P&L percentage
    hold_days=3,             # How long we held
)
```

### Helper: Log All Signals for a Decision

```python
def log_decision_signals(symbol: str, direction: str, signals: dict, acted_on: bool = True):
    """Log all signals that influenced a trading decision."""
    from src.monitoring.signal_quality_tracker import log_signal_outcome

    signal_type_map = {
        'composite_score': 'technical',
        'swing_signal': 'technical',
        'insider_signal': 'insider',
        'congressional_signal': 'congressional',
        'options_flow': 'options',
        'short_squeeze_score': 'squeeze',
        'sentiment_score': 'sentiment',
        'social_score': 'social',
    }

    for signal_name, strength in signals.items():
        if signal_name in signal_type_map and strength > 0.3:
            log_signal_outcome(
                signal_type=signal_type_map[signal_name],
                symbol=symbol,
                direction=direction,
                signal_strength=strength,
                acted_on=acted_on,
            )

# Usage:
signals = {
    'composite_score': 0.65,
    'swing_signal': 0.72,
    'insider_signal': 0.65,
}
log_decision_signals("SLB", "bullish", signals, acted_on=True)
```

## Decision Rules

### Position Sizing by Confidence
| Confidence | Size (% of portfolio) |
|------------|----------------------|
| 90%+ | 20% max |
| 75-90% | 15% max |
| 60-75% | 10% max |
| <60% | 5% max or HOLD |

**Note:** Adversarial analysis may reduce confidence and thus position size.

### CRITICAL: Thesis Position Sizing Rule (Learned 2026-01-07)

**HIGH CONVICTION ≠ HIGH CONCENTRATION**

When a thesis has multiple vehicles (e.g., services, tankers, refiners, E&P for an energy thesis):

1. **START EQUAL WEIGHT**: Allocate thesis capital equally across ALL thesis vehicles
   - Example: 6 Venezuela positions = ~6% each, not 22% SLB + 17% XLE + 1% others

2. **LET WINNERS PROVE THEMSELVES**: Only concentrate AFTER a vehicle demonstrates 10%+ outperformance
   - The market knows timing better than you do
   - Winners will naturally grow; don't force it

3. **SEPARATE IMMEDIATE vs FUTURE BENEFICIARIES**:
   - Immediate beneficiaries: Benefit NOW (e.g., tankers shipping oil)
   - Future beneficiaries: Benefit LATER (e.g., services for reconstruction)
   - Equal weight ensures you capture the right timing

4. **MAX LIMITS**:
   - Max single thesis position: 15% (not 22%)
   - Max total thesis exposure: 35% (not 39%)

**Why This Matters (from real results):**
- Actual allocation (concentrated): +0.55% ROI
- Equal weight allocation: +1.92% ROI
- Difference: ~$1,000 left on the table
- Tankers (small positions) returned +10-13%
- SLB/XLE (large positions) returned -2 to -3%

### Stop Loss Guidelines
| Type | Stop Loss |
|------|-----------|
| High conviction thesis | -15% |
| Moderate conviction | -10% |
| Speculative | -5% |

### OPTIONS DECISION TREE (NEW - Added 2026-01-08)

Clear rules for managing options positions:

```
┌─────────────────────────────────────────────────────────────┐
│                  OPTIONS DECISION TREE                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Is underlying THESIS still VALID?                           │
│  ├── NO → CUT IMMEDIATELY (regardless of P&L)               │
│  │        Thesis invalidation = exit signal                  │
│  │                                                           │
│  └── YES → Continue evaluation...                            │
│       │                                                      │
│       ├── Option down >30%?                                  │
│       │   └── HOLD - IV crush is temporary if thesis valid   │
│       │       (We held SLB calls through -50% → recovered +90%)│
│       │                                                      │
│       ├── Option up >50%?                                    │
│       │   └── Consider PARTIAL PROFIT (sell 50%)             │
│       │       Lock in gains, let rest ride                   │
│       │                                                      │
│       ├── Less than 2 weeks to expiry?                       │
│       │   └── ROLL or CLOSE - theta accelerates              │
│       │       Don't let time decay eat profits               │
│       │                                                      │
│       └── Position >5% of portfolio?                         │
│           └── TRIM to 3% max                                 │
│               Options are leveraged, limit risk              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Lesson (from Jan 7-8, 2026):**
- Options went from -50% to +30% in one day
- Panic selling at -50% would have missed +90% recovery
- IF thesis is valid, IV crush is TEMPORARY
- Hold through volatility, but set mental stops if thesis breaks

### When to HOLD (No Action)
- Confidence <50% after adversarial adjustment
- Signal + thesis misalignment
- Already at max sector exposure
- Adversary raises critical concerns
- PDT constraint would be triggered

### When to BUY
- Statistical signal + thesis alignment
- Adversary clears (low/medium concern)
- Clear exit criteria defined
- Portfolio has capacity
- Pre-mortem identifies manageable risks

### When to SELL/CLOSE
- Thesis invalidated
- Stop loss triggered
- Take profit target reached
- Adversary raises new concerns
- Better opportunity elsewhere

## Example Session

```
User: /trade-decision

Claude: I'll analyze today's context against active theses and make trading decisions.

## Context Review

**Unified State Summary:**
- Market Regime: risk-on
- S&P Futures: +0.3%
- VIX: 14.8 (calm)

**Portfolio:**
- Total Equity: $95,888
- Energy exposure: 45% (high)
- Cash available: ~$10,000

**Active Theses:**
1. Venezuela Energy Recovery (65% conviction) - SLB, HAL

**Watchlist Signals:**
- SLB: composite=0.65, swing_signal=0.72
- HAL: composite=0.58, insider_signal=0.65
- VLO: composite=0.30 (no action)

---

## Trading Decisions

### Decision 1: SLB - HOLD (despite BUY signal)

**Adversarial Analysis:**
- Concern Level: MEDIUM
- Key Issue: Already 16% SLB exposure + 45% energy sector
- Recommendation: Do not add

**Reasoning:**
Although SLB has a BUY signal and thesis is intact:
1. Already have significant SLB exposure (16%)
2. Energy sector at 45% - concentration risk
3. Adversary correctly notes adding increases drawdown risk

**Pre-mortem thought:**
"If I add more and Venezuela policy reverses, I could lose 15%+ on
an even larger position."

**Action:** HOLD
**Confidence:** 70% (in HOLD decision)

---

### Decision 2: HAL - SMALL ADD

**Adversarial Analysis:**
- Concern Level: LOW
- Key Issue: Same Venezuela thesis as SLB
- Recommendation: Proceed with reduced size

**Reasoning:**
HAL is our secondary play on Venezuela thesis:
1. Lower position than SLB - room to add
2. Insider signal confirms institutional interest
3. Diversifies within thesis (not just SLB)

**Pre-mortem:**
"If thesis fails, HAL will correlate with SLB loss. But smaller
position limits damage."

**Action:** BUY
**Size:** 3% of portfolio (~$2,900)
**Stop Loss:** -10%
**Take Profit:** +25%
**Confidence:** 65% (after adversarial)
**Thesis Link:** venezuela_energy_recovery

---

## Decisions Logged

1. SLB HOLD - No new decision logged (maintaining position)
2. HAL BUY - Decision ID: abc12345

Run /execute-trades to execute the HAL decision.
```

## Register Output as Document

Decisions are auto-indexed via `DecisionLogger.log_decision()`. If you write a separate
analysis file (e.g. a detailed trade rationale), register it:

```python
from src.db.write_api import athena_db

athena_db.save_document(
    doc_type="decision",
    title=f"Trade Analysis: BUY SLB",
    file_path=str(filepath),
    source="skill:trade-decision",
    decision_id=decision.id,
    thesis_id=thesis_id,
    symbols=["SLB"],
    tags=["decision", "buy", "thesis_driven"],
)
```

## Query Historical Context

Before making decisions, check historical documents and insights for the symbol:

```python
from src.db.write_api import athena_db

# What do we know about this symbol?
docs = athena_db.get_documents_for_symbol("SLB", limit=10)
for doc in docs:
    print(f"  [{doc.doc_type}] {doc.title} ({doc.created[:10]})")

# Any relevant research insights?
insights = athena_db.search_insights("SLB")

# Search all documents
results = athena_db.search_documents("Venezuela energy")
```

Or use the convenience script:
```bash
PYTHONPATH=. python3 scripts/context_for_symbol.py SLB
```

## Key Files

| File | Purpose |
|------|---------|
| `~/quant_results/live/state.json` | Unified state (read first) |
| `~/quant_results/theses/` | Investment theses |
| `~/quant_results/knowledge/` | Company/sector knowledge |
| `~/quant_results/decisions/` | Decision logs |
| `src/decision/adversary.py` | Adversarial agent |
| `src/knowledge/thesis.py` | Thesis tracker |
