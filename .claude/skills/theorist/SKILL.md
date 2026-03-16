---
name: theorist
description: Weekly strategic thinking — thesis review, blind spot analysis, scenario planning, forward-looking synthesis. Maintains multi-day strategic context.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Theorist Skill

Strategic thinking agent. Reviews all theses holistically, identifies portfolio blind spots, generates new thesis candidates, and scenario-plans for upcoming catalysts. Runs weekly (Sundays) and can be triggered by the Reviewer when strategic questions accumulate.

Designed to be thorough (10-15 minutes, Opus model). Writes findings to strategic context and a standalone report.

## Steps

### Step 1: Load Full Context

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
from src.swarm.situation_board import SituationBoard
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
import json
from pathlib import Path

# Strategic context — multi-day patterns and trends
ctx = StrategicContext.load()
print('=== STRATEGIC CONTEXT ===')
print(ctx.get_summary())

# Thesis momentum trends
print('\n=== THESIS MOMENTUM ===')
for name, momentum in ctx.data.get('thesis_momentum', {}).items():
    history = momentum.get('history', [])
    trend = momentum.get('trend', 'unknown')
    current = history[-1]['conviction'] if history else '?'
    print(f'  {name}: {current}% ({trend})')

# Developing patterns
patterns = ctx.data.get('developing_patterns', [])
if patterns:
    print(f'\n=== DEVELOPING PATTERNS ({len(patterns)}) ===')
    for p in patterns:
        print(f'  {p[\"name\"]} ({p.get(\"days_active\", 0)}d): {p[\"interpretation\"][:80]}')

# Upcoming catalysts
catalysts = ctx.data.get('upcoming_catalysts', [])
if catalysts:
    print(f'\n=== UPCOMING CATALYSTS ({len(catalysts)}) ===')
    for c in catalysts:
        affected = ', '.join(c.get('affected', [])[:3])
        print(f'  {c[\"date\"]}: {c[\"event\"]} ({affected})')

# Research hypotheses (open)
hypotheses = [h for h in ctx.data.get('research_hypotheses', []) if h.get('status') == 'open']
if hypotheses:
    print(f'\n=== OPEN RESEARCH HYPOTHESES ({len(hypotheses)}) ===')
    for h in hypotheses:
        print(f'  [{h[\"suggested_by\"]}] {h[\"hypothesis\"][:80]}')

# Open questions
questions = ctx.data.get('open_questions', [])
if questions:
    print(f'\n=== OPEN QUESTIONS ({len(questions)}) ===')
    for q in questions:
        print(f'  {q[\"question\"][:80]}')

# Signal source trends
source_trends = ctx.data.get('signal_source_trends', {})
if source_trends:
    print(f'\n=== SIGNAL SOURCE TRENDS ===')
    for name, info in source_trends.items():
        trend = info.get('trend', 'unknown')
        current = info.get('current_hit_rate', '?')
        print(f'  {name}: {current:.0%} ({trend})' if isinstance(current, float) else f'  {name}: {current} ({trend})')
"
```

Also load all active theses and recent reviews:

```bash
PYTHONPATH=. python3 -c "
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
from pathlib import Path
import json, glob

tracker = ThesisTracker(paths.theses)
theses = tracker.get_all_theses()

print('=== ALL ACTIVE THESES ===')
for t in sorted(theses, key=lambda x: -x.conviction):
    if t.status != 'active':
        continue
    vehicles = ', '.join(t.vehicles[:5]) if t.vehicles else 'none'
    print(f'  {t.name}: {t.conviction:.0f}% | vehicles: {vehicles}')
    if t.signposts:
        for sp in t.signposts[:2]:
            direction = sp.direction if hasattr(sp, 'direction') else '?'
            triggered = ' [TRIGGERED]' if sp.triggered else ''
            print(f'    signpost: {sp.description[:60]} ({direction}){triggered}')
"

# Recent internal reviews (last 3)
ls -t ~/quant_results/reviews/internal_review_*.json 2>/dev/null | head -3 | while read f; do
    PYTHONPATH=. python3 -c "
import json
with open('$f') as fh:
    r = json.load(fh)
status = r.get('overall_status', '?')
items = r.get('action_items', [])
print(f'Review {r.get(\"timestamp\",\"?\")[:16]}: {status} ({len(items)} action items)')
for item in items[:3]:
    print(f'  - {item}')
"
done

# Recent learnings
PYTHONPATH=. python3 -c "
from pathlib import Path
import json
from datetime import datetime
learnings_dir = paths.base / 'learnings'
if learnings_dir.exists():
    files = sorted(learnings_dir.glob('*.json'), reverse=True)[:2]
    for f in files:
        with open(f) as fh:
            data = json.load(fh)
        entries = data if isinstance(data, list) else data.get('learnings', [])
        print(f'{f.name}: {len(entries)} learnings')
        for e in entries[-5:]:
            text = e.get('learning', e.get('text', str(e)))[:80]
            print(f'  - {text}')
"
```

### Step 2: Thesis Portfolio Review

For each active thesis, assess:

1. **Conviction trajectory**: Is it rising, stable, or declining over the past week?
2. **Vehicle coverage**: Are we positioned in the best vehicles? Any missing?
3. **Position sizing**: Does sizing match conviction? Any over/under-positioned theses?
4. **Timing**: Are we early, on-time, or late to this thesis?
5. **Exit criteria**: Are signposts well-defined? Would we know when to exit?

Flag specific concerns:
- Theses with declining conviction but no position changes
- Theses with high conviction but small/no positions
- Theses where better vehicles exist than what we hold
- Theses approaching key catalyst dates without proper positioning

### Step 3: Blind Spot Analysis

Systematically check for gaps:

```bash
PYTHONPATH=. python3 -c "
from src.synthesis.state import UnifiedState
from src.core.paths import paths
import json

state = UnifiedState.load(paths.live_state)
print('=== PORTFOLIO EXPOSURE ===')
# Sector breakdown
positions = state.portfolio.positions if hasattr(state, 'portfolio') and state.portfolio else {}
print(f'Total positions: {len(positions)}')

# Check what we're NOT exposed to
all_sectors = ['Technology', 'Energy', 'Healthcare', 'Financials', 'Industrials',
               'Materials', 'Consumer Discretionary', 'Consumer Staples',
               'Utilities', 'Real Estate', 'Communication Services']
print(f'\nSectors to review for blind spots:')
for sector in all_sectors:
    print(f'  {sector}')

print('\n=== MACRO RISKS NOT HEDGED ===')
# These are common risk factors to check
risks = [
    'Interest rate spike (long duration exposure)',
    'Dollar strength (international revenue)',
    'Recession (cyclical exposure)',
    'Inflation persistence (margin compression)',
    'China slowdown (commodity demand)',
    'Credit tightening (leveraged names)',
    'Oil price collapse (energy overweight)',
    'Tech rotation (growth vs value)',
]
for risk in risks:
    print(f'  ? {risk}')
"
```

Think through:
- What narratives are strengthening that we're NOT positioned for?
- What tail risks could hurt us that we haven't hedged?
- Are there thesis interactions we're missing (e.g., two theses that are actually correlated)?
- What would the market look like in 30 days if our biggest thesis is wrong?

### Step 4: Scenario Planning

For each upcoming catalyst in strategic context:

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()

catalysts = ctx.data.get('upcoming_catalysts', [])
print('=== SCENARIO PLANNING ===')
for c in catalysts[:5]:
    print(f'\nCatalyst: {c[\"event\"]} ({c[\"date\"]})')
    affected = ', '.join(c.get('affected', []))
    print(f'  Affected: {affected}')
    print(f'  Bull: {c.get(\"scenario_bull\", \"(not defined)\")}')
    print(f'  Bear: {c.get(\"scenario_bear\", \"(not defined)\")}')
    print(f'  --> Am I positioned for BOTH outcomes?')
"
```

For each scenario:
- What's our approximate portfolio P&L in bull vs bear case?
- Are we positioned correctly for both outcomes?
- What trades would we make BEFORE the catalyst to improve positioning?
- What trades would we make AFTER each outcome materializes?

### Step 5: Generate Research Hypotheses

Based on all observations, generate testable hypotheses:

- Patterns that deserve quantitative backtesting
- Correlations that should be verified with data
- Signal source quality that needs validation
- New thesis candidates from converging observations

Write each hypothesis with a clear test plan.

### Step 6: Update Strategic Context

**CRITICAL: Write blind spots and scenarios in structured format so trade-decision and hypothesis-gen can consume them.**

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
from datetime import datetime

ctx = StrategicContext.load()

# 1. Save blind spots — trade-decision reads these in Step 0c
# ctx.data.setdefault('blind_spots', [])
# ctx.data['blind_spots'] = [
#     {'description': '<unhedged risk or missing exposure>', 'risk_level': 'high|medium|low',
#      'recommendation': '<what to do about it>', 'updated': datetime.now().isoformat()},
# ]

# 2. Save scenarios — trade-decision reads these in Step 0c
# ctx.data.setdefault('scenarios', [])
# ctx.data['scenarios'] = [
#     {'name': '<scenario name>', 'probability': '<high|medium|low>',
#      'description': '<what happens>', 'portfolio_impact': '<estimated impact>',
#      'trades_if_materializes': ['<trade 1>', '<trade 2>'],
#      'updated': datetime.now().isoformat()},
# ]

# 3. Add developing patterns found in Steps 2-3
# ctx.add_developing_pattern(
#     name='<pattern name>',
#     evidence='<what you observed>',
#     interpretation='<what it means>',
#     affected_theses=['<thesis1>', '<thesis2>'],
# )

# 4. Add catalysts identified in Step 4
# ctx.add_catalyst(
#     date='YYYY-MM-DD',
#     event='<event description>',
#     affected=['<symbol1>', '<symbol2>'],
#     scenario_bull='<bull case>',
#     scenario_bear='<bear case>',
# )

# 5. Add research hypotheses from Step 5
# ctx.add_research_hypothesis(
#     hypothesis='<testable hypothesis>',
#     suggested_by='theorist',
#     test_plan='<how to test it>',
# )

# 6. Add open strategic questions
# ctx.add_open_question('<question that needs ongoing monitoring>')

ctx.save()
print('Strategic context updated by theorist')
"
```

**Downstream consumers of theorist outputs:**
- **trade-decision Step 0c**: Reads `blind_spots` and `scenarios` to factor into decision reasoning
- **hypothesis-gen Step 2**: Converts blind spots into testable hypotheses, de-dups with existing scenarios
- **morning-briefing**: Shows developing patterns and upcoming catalysts
- **internal-review Step 6**: Tracks pattern evolution over time

### Step 7: Write Theorist Report

```bash
PYTHONPATH=. python3 -c "
import json
from datetime import datetime
from pathlib import Path

report = {
    'timestamp': datetime.now().isoformat(),
    'session_type': 'theorist',
    'thesis_reviews': [
        # For each thesis reviewed:
        # {'name': '...', 'conviction_trend': '...', 'vehicle_assessment': '...',
        #  'sizing_appropriate': True/False, 'recommendations': ['...']}
    ],
    'blind_spots': [
        # {'area': '...', 'risk_level': 'high|medium|low', 'recommendation': '...'}
    ],
    'scenario_analysis': [
        # {'catalyst': '...', 'date': '...', 'bull_pnl': '...', 'bear_pnl': '...',
        #  'positioning_adequate': True/False, 'pre_trades': ['...']}
    ],
    'new_hypotheses': [
        # {'hypothesis': '...', 'test_plan': '...', 'priority': 'high|medium|low'}
    ],
    'strategic_recommendations': [
        # Prioritized list of strategic actions
    ],
}

reviews_dir = paths.base / 'reviews'
reviews_dir.mkdir(parents=True, exist_ok=True)
filename = f'theorist_{datetime.now().strftime(\"%Y%m%d\")}.json'
with open(reviews_dir / filename, 'w') as f:
    json.dump(report, f, indent=2)
print(f'Theorist report written to {reviews_dir / filename}')
"
```

### Step 8: Write Completion

```bash
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type='theorist',
    success=True,
    summary='<1-2 sentence summary of strategic findings>',
    key_findings=['<finding 1>', '<finding 2>', '<finding 3>'],
    symbols=['<symbols with strategic implications>'],
)
print('Theorist session completion recorded')
"
```
