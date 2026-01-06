---
name: eod-review
description: End-of-day review and learning loop. Evaluates today's decisions vs outcomes, updates knowledge base with insights, and prepares for tomorrow. Run after market close (4pm+ ET).
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# EOD Review Skill

End-of-day analysis and learning loop for continuous improvement.

## Purpose

This skill:
1. Reviews today's trading decisions and outcomes
2. Compares predictions to actual results
3. Extracts lessons learned
4. Updates knowledge base with insights
5. Prepares focus areas for tomorrow

## Quick Start

```bash
# Run EOD review
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
from datetime import datetime
from src.decision.decision_logger import DecisionLogger

logger = DecisionLogger()
decisions = logger.get_today_decisions()
summary = logger.get_performance_summary(days=7)

print(f"=== EOD Review - {datetime.now().strftime('%Y-%m-%d')} ===")
print(f"Decisions today: {len(decisions)}")
print(f"7-day win rate: {summary.get('win_rate', 'N/A')}")
print(f"7-day total P&L: ${summary.get('total_pnl', 0):,.2f}")
EOF
```

## Review Process

### Step 1: Portfolio Performance

```python
from alpaca.trading.client import TradingClient
import yaml

with open("/home/nock/projects/quant_suite/config/credentials.yaml") as f:
    creds = yaml.safe_load(f)

client = TradingClient(
    creds["alpaca"]["api_key"],
    creds["alpaca"]["secret_key"],
    paper=True
)

account = client.get_account()
positions = client.get_all_positions()

# Calculate today's P&L
equity = float(account.equity)
last_equity = float(account.last_equity)
day_pnl = equity - last_equity
day_pnl_pct = (day_pnl / last_equity) * 100

print(f"Today's P&L: ${day_pnl:+,.2f} ({day_pnl_pct:+.2f}%)")
print(f"Equity: ${equity:,.2f}")
```

### Step 2: Decision Outcome Analysis

For each decision made today:

```python
from src.decision.decision_logger import DecisionLogger

logger = DecisionLogger()
decisions = logger.get_today_decisions()

for decision in decisions:
    # Get current price for symbol
    position = next((p for p in positions if p.symbol == decision.symbol), None)

    if position and decision.execution_price:
        entry = decision.execution_price
        current = float(position.current_price)
        pnl_pct = ((current - entry) / entry) * 100

        print(f"""
        Decision: {decision.action.value} {decision.symbol}
        Confidence: {decision.confidence:.0%}
        Entry: ${entry:.2f}
        Current: ${current:.2f}
        P&L: {pnl_pct:+.2f}%

        Original Reasoning:
        {decision.reasoning[:200]}...

        Key Factors: {', '.join(decision.key_factors)}

        Outcome Assessment:
        - Was reasoning correct? [Analyze]
        - Did key factors play out? [Analyze]
        - What was missed? [Analyze]
        """)
```

### Step 3: Lesson Extraction

Systematically analyze:

1. **Wins - Why did they work?**
   - Which factors were most predictive?
   - Was confidence calibrated correctly?
   - What can be repeated?

2. **Losses - Why did they fail?**
   - Was the thesis wrong or timing wrong?
   - Were risks identified but ignored?
   - What warning signs were missed?

3. **Holds that moved - Should we have acted?**
   - Stocks we didn't trade but should have
   - Signals we ignored that worked

### Step 4: Update Knowledge Base

```python
from workflows.research.knowledge_base import load_knowledge_base

kb = load_knowledge_base()

# Log insight if pattern discovered
kb.add_insight(
    category="trading_pattern",
    content="Venezuela thesis stocks (SLB, HAL) show strong pre-market correlation",
    evidence=["20260106_decision_abc123"],
    confidence=0.7,
)

kb.record_data_source_performance(
    source="insider_technical",
    source_type="signal",
    prediction_correct=True,
    alpha_generated=2.5,
    strategy_name="insider_technical",
    sharpe=1.5,
    symbols=["HAL"],
)
```

### Step 5: Prepare Tomorrow's Focus

Based on today's review:
- What worked that should continue?
- What failed that should be avoided?
- New opportunities identified?
- Risk areas to monitor?

## EOD Report Format

Save to: `/home/nock/quant_results/eod_reviews/review_YYYYMMDD.json`

```json
{
  "date": "2026-01-06",
  "account": {
    "equity": 96500,
    "day_pnl": 612,
    "day_pnl_pct": 0.64
  },
  "decisions_made": 3,
  "decisions_executed": 1,
  "outcomes": {
    "wins": 1,
    "losses": 0,
    "pending": 0
  },
  "lessons_learned": [
    "HAL followed SLB pattern as predicted",
    "Pre-market strength was good entry signal"
  ],
  "tomorrow_focus": [
    "Monitor energy sector for continuation",
    "Review Feb options expiring Friday"
  ],
  "knowledge_base_updates": [
    "Logged insider_technical performance for HAL"
  ]
}
```

## Example Session

```
User: /eod-review

Claude: Running end-of-day review for January 6, 2026.

## Portfolio Summary

| Metric | Value |
|--------|-------|
| Equity | $96,500.45 |
| Day P&L | +$611.54 (+0.64%) |
| Total P&L (inception) | -$3,500 (-3.5%) |

### vs Benchmarks
- SPY: +0.45% (we outperformed by +0.19%)
- XLE: +1.2% (we underperformed by -0.56%)

---

## Decision Analysis

### Decision 1: HAL BUY (EXECUTED)
- **Entry:** $31.97
- **Current:** $32.45
- **P&L:** +$43.20 (+1.5%)
- **Confidence was:** 68%
- **Status:** WINNING

**Analysis:**
- Reasoning was correct - HAL followed SLB higher
- Pre-market strength was good entry signal
- Thesis on Venezuela reconstruction playing out

**Lessons:**
- Insider_technical signal + Venezuela thesis = strong combination
- Entry timing at market open captured the move

### Decision 2: VLO Review (NOT EXECUTED)
- **Flagged for:** Options review
- **Actual move:** VLO +0.8%
- **Status:** Options still down, but stock recovering

**Analysis:**
- Refiner margin thesis is slower than expected
- Options time decay hurting more than stock appreciation helping

**Lessons:**
- Consider closing Feb VLO calls if they don't recover this week
- Thesis may be right but timeline wrong for options

---

## Lessons Learned

1. **Signal Quality:** insider_technical on HAL was accurate
2. **Sector Theme:** Energy thesis continues working, but options timing problematic
3. **Risk Management:** Staying disciplined on position sizing helped

## Knowledge Base Updates

Logged:
- insider_technical signal performance (+1.5% in 1 day)
- Venezuela thesis confirmation evidence

## Tomorrow's Focus

1. **Monitor:** HAL position for continuation or profit-taking
2. **Review:** Feb options (VLO, GLD) for potential exit
3. **Watch:** Energy sector breadth - are laggards catching up?
4. **Research:** Any overnight news on Venezuela/Cuba

---

Review saved to: /home/nock/quant_results/eod_reviews/review_20260106.json
```

## Learning Loop Integration

The EOD review feeds into tomorrow's decision-making:

```
/morning-briefing → reads yesterday's EOD review
/trade-decision → incorporates lessons learned
/execute-trades → validates against historical patterns
/eod-review → generates new lessons
```

## Key Files

| File | Purpose |
|------|---------|
| `/home/nock/quant_results/decisions/` | Today's decisions |
| `/home/nock/quant_results/eod_reviews/` | EOD review outputs |
| `/home/nock/quant_results/trading_logs/` | Session logs |
| `workflows/research/knowledge_base.py` | Knowledge storage |

## Performance Tracking

Track over time:
- **Win rate** by signal type, sector, confidence level
- **Alpha** vs benchmarks (SPY, sector ETFs)
- **Drawdown** patterns
- **Decision quality** (confidence calibration)
