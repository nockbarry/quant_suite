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
PYTHONPATH=. python3 << 'EOF'
from src.intelligence.context_builder import DecisionContextBuilder

# Build context for the symbol you're considering
builder = DecisionContextBuilder()
ctx = builder.build_context("SLB", setup_type="thesis_driven", thesis_id=None)
print(ctx.summary)
EOF
```

Review this context and factor it into your confidence level.

### Step 0a: Calibration Enforcement (MANDATORY)

**You MUST apply calibration adjustments to every confidence level you assign.**

```bash
PYTHONPATH=. python3 << 'EOF'
import json
from pathlib import Path

cal_path = Path.home() / "quant_results" / "intelligence" / "calibration.json"
if cal_path.exists():
    cal = json.loads(cal_path.read_text())
    print("=== CALIBRATION ENFORCEMENT ===")
    print(f"Overconfident: {cal.get('overconfident', False)}")
    print(f"Calibration error: {cal.get('calibration_error', 0):.0%}")
    print(f"Total resolved predictions: {cal.get('total_resolved', 0)}")

    # Build adjustment table from calibration bins
    print("\nConfidence Adjustment Table:")
    print(f"  {'Stated':>10s} {'Actual Hit%':>12s} {'Adjusted To':>12s}")
    print(f"  {'─'*10} {'─'*12} {'─'*12}")
    for b in cal.get("bins", []):
        predicted = b.get("predicted", 0.5)
        actual = b.get("actual", 0.5)
        n = b.get("n", 0)
        if n >= 2:  # Need at least 2 samples for meaningful adjustment
            adjusted = min(predicted, actual + 0.05)  # Allow 5% grace above actual
            print(f"  {predicted:>9.0%} {actual:>11.0%} {adjusted:>11.0%}  (n={n})")
        else:
            print(f"  {predicted:>9.0%} {actual:>11.0%}   (insufficient data, n={n})")

    if cal.get("overconfident"):
        # Calculate the maximum safe confidence
        bins_with_data = [b for b in cal.get("bins", []) if b.get("n", 0) >= 2]
        if bins_with_data:
            worst_ratio = min(b["actual"] / b["predicted"] for b in bins_with_data if b["predicted"] > 0)
            cap = min(0.75, max(0.50, worst_ratio + 0.10))
            print(f"\n  ** CONFIDENCE CAP: {cap:.0%} **")
            print(f"  Until calibration improves, cap ALL confidence levels at {cap:.0%}")
            print(f"  Example: You think 85% → assign {min(0.85, cap):.0%}")
        else:
            print("\n  ** CONFIDENCE CAP: 70% (default, insufficient calibration data) **")
else:
    print("No calibration data yet. Use default confidence levels.")
EOF
```

**RULES:**
1. Look up your stated confidence in the Adjustment Table above
2. Use the "Adjusted To" value, NOT your stated confidence
3. If the cap is 60%, you CANNOT assign confidence above 60% to ANY trade
4. Position sizing follows from the ADJUSTED confidence (not your gut feeling)
5. This cap lifts automatically as prediction accuracy improves

### Step 0b: Read Swarm Context (Today's Events + Multi-Day Patterns)

```bash
PYTHONPATH=. python3 << 'EOF'
# Situation board — what happened today so far
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load()
snap = board.data.get("market_snapshot", {})
print("=== TODAY'S SITUATION BOARD ===")
print(f"Market: SPY={snap.get('spy', 0):.1f} ({snap.get('spy_change', 0):+.1f}%), VIX={snap.get('vix', 0):.1f}, regime={snap.get('regime', '?')}")
for obs in board.data.get("today_observations", [])[-10:]:
    symbols = ", ".join(obs.get("symbols", []))
    print(f"  [{obs['time']}] {obs['source']}: {obs['text'][:100]} {symbols}")
print(f"\nDecisions already made today: {len(board.data.get('decisions_today', []))}")
for d in board.data.get("decisions_today", []):
    print(f"  {d['symbol']} {d['action']} conf={d['confidence']}")
print(f"Pending analyses: {len(board.get_pending_analyses())}")
print(f"Portfolio alerts: {len(board.data.get('portfolio_alerts', []))}")
for a in board.data.get("portfolio_alerts", [])[:5]:
    print(f"  {a['symbol']}: {a['type']} ({a.get('current_pnl', '')})")

# Strategic context — multi-day patterns
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
print("\n=== STRATEGIC CONTEXT (Multi-Day) ===")
print(ctx.get_summary())
for p in ctx.data.get("developing_patterns", [])[:3]:
    print(f"  Pattern: {p['name']} ({p.get('days_active', 0)}d) — {p['interpretation'][:80]}")
for c in ctx.data.get("upcoming_catalysts", [])[:3]:
    print(f"  Catalyst: {c['date']}: {c['event']}")
EOF
```

Use this context to understand what's already happened today and what multi-day patterns are developing. Avoid duplicating decisions already made today. Factor developing patterns and upcoming catalysts into your trade analysis.

### Step 0c: Read Analyst Assessments & Theorist Insights

**CRITICAL: Consume upstream session outputs before making decisions.**

```bash
PYTHONPATH=. python3 << 'EOF'
from src.swarm.situation_board import SituationBoard
from src.swarm.strategic_context import StrategicContext

board = SituationBoard.load()

# 1. Read analyst assessments from today (triggered by sentinel events)
print("=== ANALYST ASSESSMENTS (Today) ===")
assessments = [obs for obs in board.data.get("today_observations", [])
               if obs.get("source") == "analyst" or obs.get("obs_type") == "assessment"]
if assessments:
    for a in assessments:
        symbols = ", ".join(a.get("symbols", []))
        print(f"  [{a['time']}] {a['text'][:120]}")
        if symbols:
            print(f"    Symbols: {symbols}")
        if a.get("action"):
            print(f"    Recommendation: {a['action']}")
else:
    print("  (No analyst assessments today)")

# 2. Read theorist blind spots and scenario analysis from strategic context
ctx = StrategicContext.load()
print("\n=== THEORIST BLIND SPOTS ===")
blind_spots = ctx.data.get("blind_spots", [])
if blind_spots:
    for bs in blind_spots[:5]:
        print(f"  - {bs.get('description', bs) if isinstance(bs, dict) else bs}")
else:
    print("  (No blind spots flagged)")

print("\n=== THEORIST SCENARIOS ===")
scenarios = ctx.data.get("scenarios", [])
if scenarios:
    for s in scenarios[:3]:
        print(f"  [{s.get('probability', '?')}] {s.get('name', '?')}: {s.get('description', '')[:80]}")
else:
    print("  (No active scenarios)")

# 3. Read evening-research findings from last night
print("\n=== EVENING RESEARCH FINDINGS ===")
from pathlib import Path
from datetime import datetime, timedelta
import json

reviews_dir = Path.home() / "quant_results" / "reviews"
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
today = datetime.now().strftime("%Y%m%d")

for date_str in [today, yesterday]:
    report_path = reviews_dir / f"evening_research_{date_str}.json"
    if report_path.exists():
        with open(report_path) as f:
            report = json.load(f)
        findings = report.get("web_findings", [])
        actionable = [f for f in findings if f.get("actionable")]
        if actionable:
            print(f"  Actionable findings ({date_str}):")
            for finding in actionable[:5]:
                print(f"    - [{finding.get('topic', '?')}] {finding.get('finding', '')[:80]}")
                if finding.get("affected_theses"):
                    print(f"      Theses: {', '.join(finding['affected_theses'])}")
                if finding.get("conviction_impact") != "neutral":
                    print(f"      Conviction: {finding.get('conviction_impact', '?')}")
        watch = report.get("tomorrow_watch", [])
        if watch:
            print(f"  Tomorrow watch list:")
            for w in watch[:5]:
                print(f"    - {w[:80]}")
        break
else:
    print("  (No evening research report found)")
EOF
```

```bash
# Log artifact reads for flow health monitoring
PYTHONPATH=. python3 << 'EOF'
from src.swarm.artifact_log import log_artifact_read
from pathlib import Path

log_artifact_read("trade-decision", "analyst_assessment", detail="checked situation board")
log_artifact_read("trade-decision", "theorist_blind_spots", detail="checked strategic context")
cal_path = Path.home() / "quant_results" / "intelligence" / "calibration.json"
log_artifact_read("trade-decision", "calibration", str(cal_path), found=cal_path.exists())
EOF
```

**Factor these upstream insights into your decisions:**
- If an analyst flagged a symbol as `recommend_trade`, prioritize analyzing it
- If the theorist flagged blind spots, address them explicitly in your reasoning
- If evening research found actionable news, check if it changes thesis conviction

### Step 1: Load Context

```bash
PYTHONPATH=. python3 << 'EOF'
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

    # NEWS INTELLIGENCE — thesis-matched headlines from automated pipeline
    print("\n=== THESIS-MATCHED NEWS ===")
    for news in state.news_events[:10]:
        print(f"  [{news.get('source','')}] {news.get('headline','')[:80]}")
        for tid, match in news.get('thesis_matches', {}).items():
            print(f"    → {match['name']} ({match.get('direction','neutral')}, {match.get('relevance',0):.0%})")

    print("\n=== URGENT NEWS ALERTS ===")
    for alert in state.news_urgency_alerts[:5]:
        urgency = alert.get('urgency', 'medium')
        headline = alert.get('headline', '')[:80]
        print(f"  [{urgency.upper()}] {headline}")
        if alert.get('thesis_matches'):
            names = [m['name'] for m in alert['thesis_matches'].values()]
            print(f"    Theses: {', '.join(names)}")
EOF
```

**IMPORTANT:** Factor thesis-matched news into your trading decisions. Headlines that match
active theses with relevance > 0.5 are strong catalysts — check if they confirm or
challenge your thesis before trading.

### Step 2: Review Knowledge Base

```bash
PYTHONPATH=. python3 << 'EOF'
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
PYTHONPATH=. python3 << 'EOF'
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

## Context Preservation

**IMPORTANT:** Push context to SessionContext so it's automatically attached to decisions.

```python
from src.context.session_context import SessionContext
from src.context.market_snapshot import capture_market_snapshot

ctx = SessionContext.get()

# At start of trade decision session
ctx.add_market_snapshot(capture_market_snapshot())

# After web searches for news/research
ctx.add_web_search(query="...", results_summary="...", symbols=["SLB"])

# After adversarial analysis
ctx.add_reasoning_step("adversarial", "Concern level: MEDIUM. Key issue: ...", symbols=["SLB"])

# After pre-mortem
ctx.add_reasoning_step("pre_mortem", "If thesis fails, HAL correlates with SLB loss.", symbols=["HAL"])

# After agent outputs (research, critic)
ctx.add_agent_output(agent_type="critic", agent_id="...", summary="...", key_findings=["..."])
```

This context is **automatically merged** into `DecisionRecord.context` when `create_decision()` is called.

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

# 4b. Record decision on situation board for cross-session awareness
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load_or_create()
board.add_decision(
    symbol=decision.symbol,
    action=decision.action.value,
    confidence=decision.confidence,
    status="pending",
    reasoning_summary=decision.reasoning[:100] if decision.reasoning else "",
)
board.save()

# 4c. Set/update price targets for the vehicle (ALWAYS do this on BUY/ADD)
# Use your thesis knowledge to estimate bull/base/bear scenarios
current_price = 47.50  # Get from quote or state.json
tracker.set_price_targets(thesis_id, {
    "SLB": {
        "bull_target": 62.00,    # Best case: Venezuela contracts + oil $85
        "base_target": 55.00,    # Most likely: gradual recovery
        "bear_target": 40.00,    # Downside: policy reversal
        "entry_price": current_price,
        "timeframe_days": 90,
        "notes": "Venezuela reconstruction + Hormuz disruption upside",
    },
})
# This auto-creates a price_target PredictionRecord that gets scored daily

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

**Note:** If you set price targets in Step 4c, `price_target` predictions are
auto-created. You only need to manually log predictions for additional things like
event outcomes, timeframe-specific moves, or thesis validation.

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

Decision will be auto-executed by cron_auto_execute.py after this session completes.
```

## Step 8: Auto-Execution (Autonomous Mode)

**Decisions are automatically executed after this session completes.**

The `session_wrapper.sh` calls `cron_auto_execute.py` after every `/trade-decision` session,
which finds all PENDING decisions from the last 4 hours and executes them on paper account.

**No `/execute-trades` skill invocation needed.** The pipeline is:
1. `/trade-decision` creates decisions with status PENDING
2. `session_wrapper.sh` calls `cron_auto_execute.py`
3. `cron_auto_execute.py` validates risk limits and executes

**Safety rails enforced by auto-execute:**
- Max 10% single position
- Paper account only (live requires explicit override)
- Equity > $1,000
- Valid price quote required

If you want to execute immediately within this session instead of waiting:

```bash
PYTHONPATH=. python3 scripts/cron_auto_execute.py
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
