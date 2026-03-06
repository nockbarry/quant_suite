---
name: analyst
description: Fast event-driven analysis triggered by Sentinel. Reads situation board and strategic context, assesses pending analysis requests, writes assessments back to the board.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Analyst Skill

Fast event assessment triggered by the Sentinel daemon when market events need LLM interpretation. Reads pending analysis requests from the situation board, assesses each one against today's observations and multi-day strategic context, and writes actionable assessments back.

Designed to be short (3-5 minutes, Sonnet model). One question in, one assessment out.

## Steps

### Step 1: Read Context

```bash
PYTHONPATH=. python3 -c "
from src.swarm.situation_board import SituationBoard
from src.swarm.strategic_context import StrategicContext
import json

# Load situation board
board = SituationBoard.load()
print('=== SITUATION BOARD ===')
snap = board.data.get('market_snapshot', {})
print(f'Market: SPY={snap.get(\"spy\", 0):.1f} ({snap.get(\"spy_change\", 0):+.1f}%), VIX={snap.get(\"vix\", 0):.1f}, regime={snap.get(\"regime\", \"?\")}')

print(f'\nToday ({len(board.data.get(\"today_observations\", []))} observations):')
for obs in board.data.get('today_observations', [])[-10:]:
    symbols = ', '.join(obs.get('symbols', []))
    thesis = f' [{obs[\"thesis\"]}]' if obs.get('thesis') else ''
    print(f'  [{obs[\"time\"]}] {obs[\"source\"]}: {obs[\"text\"][:100]}{thesis} {symbols}')

print(f'\nDecisions today: {len(board.data.get(\"decisions_today\", []))}')
for d in board.data.get('decisions_today', []):
    print(f'  {d[\"symbol\"]} {d[\"action\"]} conf={d[\"confidence\"]} ({d[\"status\"]})')

print(f'\nPortfolio alerts: {len(board.data.get(\"portfolio_alerts\", []))}')
for a in board.data.get('portfolio_alerts', [])[:5]:
    print(f'  {a[\"symbol\"]}: {a[\"type\"]} ({a.get(\"current_pnl\", \"\")})')

# Pending analyses
pending = board.get_pending_analyses()
print(f'\n=== PENDING ANALYSES ({len(pending)}) ===')
for p in pending:
    print(f'  [{p[\"id\"]}] trigger={p[\"trigger\"]}: {p[\"context\"]}')

# Load strategic context
ctx = StrategicContext.load()
print('\n=== STRATEGIC CONTEXT ===')
print(ctx.get_summary())

# Show relevant patterns
patterns = ctx.data.get('developing_patterns', [])
if patterns:
    print(f'\nDeveloping patterns:')
    for p in patterns[:5]:
        print(f'  {p[\"name\"]} ({p.get(\"days_active\", 0)}d): {p[\"interpretation\"][:80]}')

# Show relevant catalysts
catalysts = ctx.data.get('upcoming_catalysts', [])
if catalysts:
    print(f'\nUpcoming catalysts:')
    for c in catalysts[:5]:
        print(f'  {c[\"date\"]}: {c[\"event\"]} ({\", \".join(c.get(\"affected\", [])[:3])})')
"
```

If there are no pending analyses, also check the situation board for unassessed observations that might need attention (new convergences, urgent news, significant position moves).

### Step 2: Assess Each Pending Analysis

For each pending analysis request, systematically evaluate:

1. **What happened**: Summarize the event/trigger in one sentence
2. **Thesis alignment**: Does this relate to any active thesis? Which ones?
3. **Historical context**: Have we seen similar patterns? What happened?
4. **Signal quality**: Is this from a reliable source? Multiple confirmations?
5. **Actionability**: Should we trade, monitor, or dismiss?
6. **Risk**: What could go wrong if we act on this?

Classification framework:
- **recommend_trade**: Strong multi-signal alignment, thesis-supported, clear risk/reward
- **monitor**: Interesting but needs more confirmation or context
- **dismiss**: Noise, already priced in, or unreliable source

### Step 3: Write Assessments to Board

For each assessment:

```bash
PYTHONPATH=. python3 -c "
from src.swarm.situation_board import SituationBoard

board = SituationBoard.load()

# Write your assessment
board.add_observation(
    source='analyst',
    obs_type='assessment',
    text='<your assessment — 1-2 sentences>',
    symbols=['<affected symbols>'],
    thesis='<related thesis name if any>',
    action='<recommend_trade|monitor|dismiss>',
)

# Mark the analysis as consumed
board.consume_analysis('<analysis_id>')

board.save()
print('Assessment written to situation board')
"
```

### Step 4: Flag for Strategist if Actionable

If any assessment recommends a trade:

```bash
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_trade_trigger

write_trade_trigger(
    symbol='<symbol>',
    direction='<bullish|bearish>',
    signal_count=<number of aligned signals>,
    signals=[
        {'source': '<source1>', 'detail': '<detail>'},
        {'source': '<source2>', 'detail': '<detail>'},
    ],
    source='analyst',
)
print('Trade trigger written — sentinel/health_monitor will launch trade-decision')
"
```

The Sentinel or health monitor will detect the trigger and launch a trade-decision session.

### Step 5: Update Strategic Context (if patterns spotted)

If you notice developing multi-day patterns while assessing:

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext

ctx = StrategicContext.load()

# Add developing pattern if you spot a multi-day trend
ctx.add_developing_pattern(
    name='<pattern name>',
    evidence='<what you observed today>',
    interpretation='<what it means>',
    affected_theses=['<thesis1>', '<thesis2>'],
)

# Add research hypothesis if something needs quantitative testing
ctx.add_research_hypothesis(
    hypothesis='<testable hypothesis>',
    suggested_by='analyst',
    test_plan='<how to test it>',
)

ctx.save()
"
```

### Step 6: Write Completion

```bash
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type='analyst',
    success=True,
    summary='<1-2 sentence summary of assessments made>',
    key_findings=['<finding 1>', '<finding 2>'],
    symbols=['<symbols analyzed>'],
)
"
```
