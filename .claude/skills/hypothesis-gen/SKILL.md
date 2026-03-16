---
name: hypothesis-gen
description: Generate testable hypotheses from accumulated signals, convergences, and observations. Reads all data sources and strategic context, then produces 5-10 falsifiable predictions with specific triggers and test plans.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Hypothesis Generation Skill

Weekly ideation session that transforms accumulated data into testable hypotheses. Reads signals, convergences, thesis performance, prediction outcomes, and market patterns, then generates novel hypotheses for the research pipeline.

Designed to run weekly (Sundays 5 PM) and after major market events.

## Step 1: Load All Signal Sources

```bash
PYTHONPATH=. python3 -c "
from src.synthesis.state import UnifiedState
from src.swarm.situation_board import SituationBoard
from src.swarm.strategic_context import StrategicContext
from src.core.paths import paths
import json, sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Current state
state = UnifiedState.load(paths.live_state)
print('=== PORTFOLIO STATE ===')
print(state.get_summary())

# Signal digest
digest_file = paths.base / 'live' / 'signal_digest.json'
if digest_file.exists():
    with open(digest_file) as f:
        digest = json.load(f)
    convergences = digest.get('convergences', [])
    print(f'\n=== SIGNAL CONVERGENCES ({len(convergences)}) ===')
    for c in convergences[:10]:
        print(f'  {c.get(\"symbol\", \"?\")} [{c.get(\"source_count\", 0)} sources]: {c.get(\"summary\", \"\")}')

# Recent predictions and their outcomes
print('\n=== PREDICTION OUTCOMES (last 30 days) ===')
conn = sqlite3.connect(str(paths.base / 'athena.db'))
scored = conn.execute('''
    SELECT symbol, prediction_type, direction, status, accuracy_score, resolution_notes
    FROM predictions
    WHERE status IN ('hit', 'miss')
    ORDER BY resolved_at DESC LIMIT 15
''').fetchall()
for r in scored:
    print(f'  {r[0]:6s} {r[1]:16s} {r[2]:8s} -> {r[3]:4s} (acc={r[4]}) {(r[5] or \"\")[:60]}')

# Thesis momentum
print('\n=== THESIS MOMENTUM ===')
ctx = StrategicContext.load()
momentum = ctx.data.get('thesis_momentum', {})
for name, m in sorted(momentum.items(), key=lambda x: x[1].get('trend', ''))[:15]:
    hist = m.get('conviction_history', [])
    latest = hist[-1]['conviction'] if hist else '?'
    print(f'  {name[:35]:35s} trend={m.get(\"trend\", \"?\"):12s} conv={latest}')

# Market movers
movers_file = paths.base / 'live' / 'market_movers_latest.json'
if movers_file.exists():
    with open(movers_file) as f:
        movers = json.load(f)
    top = movers.get('movers', [])[:8]
    print(f'\n=== TOP MARKET MOVERS ({len(movers.get(\"movers\", []))}) ===')
    for m in top:
        print(f'  {m.get(\"symbol\", \"?\")} {m.get(\"day_change_pct\", 0):+.1f}% ctx={m.get(\"context_score\", 0):.0f}% {m.get(\"reason\", \"\")[:50]}')

conn.close()
"
```

## Step 2: Review Existing Hypotheses & Upstream Inputs

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
from pathlib import Path
import json

ctx = StrategicContext.load()

# 1. Existing hypotheses (avoid duplicates)
hypotheses = ctx.data.get('research_hypotheses', [])
print(f'=== EXISTING HYPOTHESES ({len(hypotheses)}) ===')
for h in hypotheses:
    print(f'  [{h.get(\"status\", \"?\")}] {h.get(\"id\", \"?\")} — {h.get(\"hypothesis\", \"?\")[:80]}')
    if h.get('finding'):
        print(f'    finding: {h[\"finding\"][:80]}')

# 2. Theorist scenarios and blind spots (don't duplicate these)
print(f'\n=== THEORIST SCENARIOS (de-dup with) ===')
for s in ctx.data.get('scenarios', [])[:5]:
    print(f'  [{s.get(\"probability\", \"?\")}] {s.get(\"name\", \"?\")}: {s.get(\"description\", \"\")[:80]}')
blind_spots = ctx.data.get('blind_spots', [])
if blind_spots:
    print(f'\n=== THEORIST BLIND SPOTS (generate hypotheses for) ===')
    for bs in blind_spots[:5]:
        desc = bs.get('description', bs) if isinstance(bs, dict) else bs
        print(f'  - {desc}')

# 3. Internal review action items (investigate-type items become hypotheses)
print(f'\n=== INTERNAL REVIEW ACTION ITEMS ===')
reviews_dir = paths.base / 'reviews'
review_files = sorted(reviews_dir.glob('internal_review_*.json'), key=lambda p: p.name, reverse=True)
if review_files:
    with open(review_files[0]) as f:
        review = json.load(f)
    for item in review.get('action_items', []):
        lower = item.lower()
        if any(kw in lower for kw in ['investigate', 'research', 'test', 'check why', 'verify', 'explore']):
            print(f'  RESEARCH: {item[:80]}')
        else:
            print(f'  (non-research) {item[:80]}')

# 4. Research queue — what's already queued
print(f'\n=== EXISTING RESEARCH QUEUE ===')
queue_file = paths.base / 'scheduler' / 'research_queue.json'
if queue_file.exists():
    with open(queue_file) as f:
        queue = json.load(f)
    for task in queue:
        print(f'  [{task.get(\"priority\", \"?\")}] {task.get(\"description\", \"?\")[:60]} ({task.get(\"type\", \"?\")}) symbols={task.get(\"symbols\", [])}')
    if not queue:
        print('  (empty)')
else:
    print('  (no queue file)')

# 5. Check what research has been done
research_dir = paths.base / 'live' / 'research'
print(f'\n=== RECENT RESEARCH FILES ===')
for f in sorted(research_dir.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
    print(f'  {f.name} ({f.stat().st_size/1024:.0f}KB)')
"
```

**De-duplication rules:**
- Don't create hypotheses that overlap with existing theorist scenarios
- Convert theorist blind spots into testable hypotheses (this is the primary input)
- Convert internal-review "investigate" action items into research hypotheses
- Don't queue research tasks that already exist in the research queue

## Step 3: Generate New Hypotheses

Based on all the data above, generate **5-10 testable hypotheses**. Each must include:

### Hypothesis Template

For each hypothesis, provide:

1. **Statement**: A clear, falsifiable prediction (not "X might happen" but "X will happen within Y timeframe if Z condition is met")
2. **Evidence base**: What signals, data, or patterns support this?
3. **Test method**: How to validate — backtest with historical data? Monitor price action? Check specific data point?
4. **Timeframe**: When should we check? (1 week, 1 month, specific date)
5. **Success criteria**: What specific outcome confirms or rejects this?
6. **Affected theses**: Which existing theses does this support or challenge?
7. **Trading implication**: If confirmed, what trade would we make?

### Categories to explore:

- **Cross-signal patterns**: Do 3+ signals converging on a symbol predict 5-day returns?
- **Thesis timing**: When signposts trigger, what's the optimal entry window?
- **Prediction calibration**: Based on scored predictions, where are we systematically overconfident or underconfident?
- **Sector rotation**: What sector relative strength patterns predict future performance?
- **Contrarian signals**: Where is the portfolio most vulnerable? What would a bear case look like?
- **Novel correlations**: Unusual relationships between portfolio positions and macro indicators
- **Missing vehicles**: Are there better ways to express existing theses?
- **Regime transitions**: What signals precede regime changes? Can we position earlier?

## Step 4: Save Hypotheses to Strategic Context

```python
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext

ctx = StrategicContext.load()

# Add each hypothesis — uncomment and fill in
# ctx.add_research_hypothesis(
#     hypothesis='<FILL: Clear, falsifiable statement>',
#     suggested_by='hypothesis-gen',
#     test_plan='<FILL: How to test — backtest, monitor, or data check>',
# )

ctx.save()
print('Hypotheses saved to strategic context')
"
```

## Step 5: Flag Hypotheses for Automated Testing

For hypotheses that can be backtested automatically, create research tasks:

```python
PYTHONPATH=. python3 -c "
import json
from datetime import datetime
from pathlib import Path

# Write research queue for the research-agent to pick up
queue_file = paths.base / 'scheduler' / 'research_queue.json'
queue = []
if queue_file.exists():
    with open(queue_file) as f:
        queue = json.load(f)

# Append new research tasks
# queue.append({
#     'hypothesis_id': 'h_XXX',
#     'type': 'backtest',  # backtest, data_check, monitor
#     'description': '<what to test>',
#     'symbols': ['<symbols>'],
#     'priority': 'high',  # high, medium, low
#     'created': datetime.now().isoformat(),
# })

with open(queue_file, 'w') as f:
    json.dump(queue, f, indent=2)
print(f'Research queue: {len(queue)} tasks')
"
```

## Step 6: Write Completion Record

```python
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type='hypothesis-gen',
    success=True,
    summary='<2-3 sentences: how many hypotheses generated, key themes>',
    key_findings=['<hypothesis 1 summary>', '<hypothesis 2 summary>'],
    symbols=['<symbols mentioned in hypotheses>'],
)
"
```
