---
name: evening-research
description: Post-market web research, news synthesis, and macro analysis. Discovers information not captured by RSS feeds, generates hypotheses, and updates strategic context.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, WebSearch, WebFetch
---

# Evening Research Skill

Daily post-market research session (5:45 PM ET). Uses web search to find breaking news, analyst commentary, and macro developments that RSS feeds miss. Generates testable hypotheses for the research pipeline.

Designed to be thorough (15 minutes, Opus model with web access).

## Steps

### Step 1: Load Today's Context

```bash
PYTHONPATH=. python3 -c "
from src.synthesis.state import UnifiedState
from src.swarm.situation_board import SituationBoard
from src.swarm.strategic_context import StrategicContext
from src.core.paths import paths
import json, glob
from pathlib import Path
from datetime import datetime

# Unified state summary
state = UnifiedState.load(paths.live_state)
print('=== PORTFOLIO SNAPSHOT ===')
print(state.get_summary())

# Today's situation board
print('\n=== SITUATION BOARD ===')
board = SituationBoard.load()
print(board.get_summary())

# Strategic context
print('\n=== STRATEGIC CONTEXT ===')
ctx = StrategicContext.load()
print(ctx.get_summary())

# Today's session completions
print('\n=== TODAY SESSION COMPLETIONS ===')
today = datetime.now().strftime('%Y%m%d')
comp_dir = Path.home() / 'quant_results' / 'scheduler' / 'completions'
for f in sorted(comp_dir.glob(f'*_{today}*.json')):
    with open(f) as fh:
        c = json.load(fh)
    summary = c.get('summary', 'no summary')[:100]
    findings = c.get('key_findings', [])[:3]
    print(f'  {f.stem}: {summary}')
    for finding in findings:
        print(f'    - {finding[:80]}')
"
```

### Step 2: Gather Active Thesis Topics

```bash
PYTHONPATH=. python3 -c "
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

tracker = ThesisTracker(paths.theses)
theses = [t for t in tracker.get_all_theses() if t.status == 'active' and t.conviction >= 50]

print('=== ACTIVE HIGH-CONVICTION THESES ===')
for t in sorted(theses, key=lambda x: -x.conviction):
    vehicles = ', '.join(t.vehicles[:5]) if t.vehicles else 'none'
    print(f'  {t.name} ({t.conviction:.0f}%): {vehicles}')
    if t.signposts:
        for sp in t.signposts[:2]:
            if not sp.triggered:
                print(f'    watch: {sp.description[:60]}')
"
```

### Step 3: Web Research

Search for breaking news and developments on active thesis topics. Focus on information that RSS feeds miss:

1. **After-hours moves**: Search for after-hours earnings, guidance changes, analyst upgrades/downgrades on portfolio symbols
2. **Thesis-specific developments**: For each high-conviction thesis, search for the latest developments:
   - Geopolitical events (Iran, Venezuela, defense spending, etc.)
   - Commodity price drivers (oil, gold, copper, fertilizer, uranium)
   - Sector-specific news (semiconductors, AI infrastructure, shipping, etc.)
   - Regulatory/policy changes (sanctions, trade policy, Fed, SCOTUS)
3. **Macro context**: Search for:
   - Fed commentary and rate expectations
   - Economic data releases (today and upcoming this week)
   - Credit market stress signals
   - Global market reactions (Asia, Europe overnight moves)
4. **Contrarian signals**: Search for bearish takes on our biggest positions, short interest changes, analyst downgrades

For each search, note:
- **Source quality**: Analyst report vs blog vs social media
- **Timeliness**: Breaking today vs rehash of old news
- **Actionability**: Does this change conviction on any thesis?

### Step 3b: Push Urgent Findings to Situation Board

**If web research uncovers time-sensitive information, push it to the situation board immediately — don't wait until Step 6.** This ensures the morning briefing and any after-hours sessions see it.

```bash
PYTHONPATH=. python3 -c "
from src.swarm.situation_board import SituationBoard

board = SituationBoard.load_or_create()

# Push urgent findings as they're discovered (fill in from web research):
#
# board.add_observation(
#     source='evening-research',
#     obs_type='urgent_finding',
#     text='<finding that changes conviction or requires immediate attention>',
#     symbols=['<affected symbols>'],
# )
#
# Examples of urgent findings worth pushing immediately:
# - After-hours earnings miss/beat for a portfolio position
# - Geopolitical escalation affecting active theses
# - Analyst upgrade/downgrade on a major holding
# - Regulatory action or policy change affecting a thesis
# - Commodity price spike/crash after hours

board.save()
"
```

### Step 4: Cross-Reference with Existing Data

```bash
PYTHONPATH=. python3 -c "
from pathlib import Path
import json

# Check what news we already captured via RSS
news_cache = Path.home() / 'quant_results' / 'live' / 'news_cache.json'
if news_cache.exists():
    with open(news_cache) as f:
        cache = json.load(f)
    all_headlines = []
    for source, items in cache.items():
        if isinstance(items, list):
            for item in items:
                title = item.get('title', '')
                if title:
                    all_headlines.append(title)
    print(f'RSS captured {len(all_headlines)} headlines today')
    print('Recent headlines:')
    for h in all_headlines[:15]:
        print(f'  - {h[:80]}')
else:
    print('No news cache found')

# Check market movers
movers = Path.home() / 'quant_results' / 'live' / 'market_movers_latest.json'
if movers.exists():
    with open(movers) as f:
        data = json.load(f)
    print(f'\nMarket movers: {len(data.get(\"movers\", []))} symbols with context')
"
```

Identify gaps: What did web research surface that RSS missed? These are the highest-value findings.

### Step 5: Generate Hypotheses

Based on today's market action + web research, generate 2-3 testable hypotheses:

Each hypothesis should include:
- **Statement**: Clear, falsifiable prediction
- **Evidence**: What data supports this?
- **Test plan**: How to validate (backtest, monitor price, check data)
- **Timeline**: When should we check if this played out?
- **Affected theses**: Which existing theses does this impact?

### Step 6: Update Strategic Context

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext

ctx = StrategicContext.load()

# Add catalysts discovered during research
# ctx.add_catalyst(
#     date='YYYY-MM-DD',
#     event='<catalyst description>',
#     affected=['<symbol1>', '<symbol2>'],
#     scenario_bull='<bull outcome>',
#     scenario_bear='<bear outcome>',
# )

# Add developing patterns
# ctx.add_developing_pattern(
#     name='<pattern name>',
#     evidence='<what you found>',
#     interpretation='<what it means for portfolio>',
#     affected_theses=['<thesis1>'],
# )

# Add research hypotheses
# ctx.add_research_hypothesis(
#     hypothesis='<testable hypothesis>',
#     suggested_by='evening-research',
#     test_plan='<how to test>',
# )

ctx.save()
print('Strategic context updated by evening-research')
"
```

### Step 7: Write Evening Research Report

```bash
PYTHONPATH=. python3 -c "
import json
from datetime import datetime
from pathlib import Path

report = {
    'timestamp': datetime.now().isoformat(),
    'session_type': 'evening-research',
    'market_summary': '<1-2 sentences on today market action>',
    'web_findings': [
        # {'topic': '...', 'source': '...', 'finding': '...', 'actionable': True/False,
        #  'affected_theses': ['...'], 'conviction_impact': 'up|down|neutral'}
    ],
    'rss_gaps': [
        # Items found via web search that RSS missed
    ],
    'macro_context': {
        # 'fed': '...', 'rates': '...', 'dollar': '...', 'global': '...'
    },
    'hypotheses': [
        # {'hypothesis': '...', 'evidence': '...', 'test_plan': '...', 'timeline': '...'}
    ],
    'tomorrow_watch': [
        # Key items to monitor tomorrow
    ],
    'conviction_changes': [
        # {'thesis': '...', 'direction': 'up|down', 'reason': '...'}
    ],
}

reviews_dir = Path.home() / 'quant_results' / 'reviews'
reviews_dir.mkdir(parents=True, exist_ok=True)
filename = f'evening_research_{datetime.now().strftime(\"%Y%m%d\")}.json'
with open(reviews_dir / filename, 'w') as f:
    json.dump(report, f, indent=2)
print(f'Evening research report written to {reviews_dir / filename}')
"
```

### Step 8: Write Completion

```bash
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type='evening-research',
    success=True,
    summary='<2-3 sentence summary of key web research findings>',
    key_findings=['<finding 1>', '<finding 2>', '<finding 3>'],
    symbols=['<symbols with new information>'],
)
print('Evening research session completion recorded')
"
```
