---
name: system-review
description: Weekly autonomous self-evaluation. Reviews performance, compares instances, validates theses, and makes strategic corrections. The system's mechanism for improving itself.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, WebSearch, WebFetch
---

# System Review Skill

Weekly self-improvement session (Sunday 4:30 PM ET, Opus, 30 min).
Evaluates the trading system's performance, compares parallel instances,
and makes corrections to improve future operation.

## Step 1: Load Week's Data

Read all system outputs from the past week:
```python
PYTHONPATH=. python3 -c "
from src.core.paths import paths
from datetime import datetime, timedelta
import json

# Meta-observer reports (cross-instance comparison)
meta_dir = paths.parallel
meta_reports = sorted(meta_dir.glob('meta_report_*.json'))[-5:]
for f in meta_reports:
    with open(f) as fh:
        d = json.load(fh)
    print(f'Meta {f.name}: {d.get(\"num_instances\",0)} instances, overlap={d.get(\"thesis_overlap_jaccard\",0):.0%}')

# Stress test reports
risk_dir = paths.risk_reports
risk_reports = sorted(risk_dir.glob('stress_test_*.json'))[-3:]
for f in risk_reports:
    with open(f) as fh:
        d = json.load(fh)
    print(f'Stress {f.name}: VaR95={d.get(\"var_95_pct\",0):.1f}%, concentration={d.get(\"concentration_risk_score\",0):.2f}')

# Cross-reference alerts
alerts_file = paths.live / 'cross_reference_alerts.json'
if alerts_file.exists():
    with open(alerts_file) as fh:
        d = json.load(fh)
    print(f'Cross-ref alerts: {d.get(\"total_alerts\",0)} total, {d.get(\"red_flags\",0)} red flags')

# Auto-correction log (last 7 days)
corrections_log = paths.logs / 'auto_corrections.jsonl'
if corrections_log.exists():
    cutoff = datetime.now() - timedelta(days=7)
    week_corrections = []
    for line in open(corrections_log):
        try:
            entry = json.loads(line.strip())
            ts = datetime.fromisoformat(entry.get('timestamp',''))
            if ts >= cutoff:
                week_corrections.append(entry)
        except (json.JSONDecodeError, ValueError):
            pass
    applied = [c for c in week_corrections if c.get('applied')]
    print(f'Auto-corrections this week: {len(week_corrections)} total, {len(applied)} applied')
    for c in applied[-5:]:
        print(f'  [{c[\"action_type\"]}] {c[\"thesis_name\"]}: {c[\"reason\"][:60]}')

# Prediction accuracy
intel_dir = paths.intelligence
daily_updates = sorted(intel_dir.glob('daily_update_*.json'))[-5:]
for f in daily_updates:
    with open(f) as fh:
        d = json.load(fh)
    suggestions = d.get('thesis_suggestions', [])
    cal = d.get('calibration', {})
    print(f'Belief {f.name}: {len(suggestions)} thesis suggestions, calibration={cal.get(\"overall_accuracy\",\"?\")}'[:80])

# Learning log
from pathlib import Path
learnings_month = datetime.now().strftime('%Y-%m')
learnings_file = paths.learnings / f'{learnings_month}.json'
if learnings_file.exists():
    with open(learnings_file) as fh:
        learnings = json.load(fh)
    print(f'Learnings this month: {len(learnings) if isinstance(learnings, list) else \"dict\"}')
"
```

## Step 2: Performance Comparison

Compare all instances' weekly returns vs SPY:
```python
PYTHONPATH=. python3 -c "
from src.core.paths import paths
import json
from pathlib import Path

# Load instance state files for comparison
instances = ['auto', 'beta', 'gamma']
instance_data = {}
for inst in instances:
    if inst == 'auto':
        state_path = paths.live_state
    else:
        state_path = Path.home() / f'quant_results_{inst}' / 'live' / 'state.json'
    if state_path.exists():
        with open(state_path) as f:
            data = json.load(f)
        portfolio = data.get('portfolio', {})
        print(f'Instance {inst}: equity=\${portfolio.get(\"equity\",0):,.0f}, '
              f'cash=\${portfolio.get(\"cash\",0):,.0f}, '
              f'positions={portfolio.get(\"total_positions\",0)}, '
              f'day_pnl=\${portfolio.get(\"daily_pnl\",0):,.0f}')
        instance_data[inst] = data
    else:
        print(f'Instance {inst}: no state file found')

# Meta-observer latest report for cross-instance comparison
meta_reports = sorted(paths.parallel.glob('meta_report_*.json'))
if meta_reports:
    with open(meta_reports[-1]) as f:
        meta = json.load(f)
    print(f'\\nMeta-observer: {meta.get(\"num_instances\",0)} instances')
    consensus = meta.get('consensus_positions', [])
    divergent = meta.get('divergent_positions', [])
    print(f'  Consensus positions (all agree): {consensus[:10]}')
    print(f'  Divergent positions (disagreement): {divergent[:10]}')
    print(f'  Thesis overlap (Jaccard): {meta.get(\"thesis_overlap_jaccard\",0):.0%}')
"
```

Answer these questions in your analysis:
- Which instance had the highest Sharpe this week?
- Did consensus positions (held by all 3) outperform divergent positions?
- What was the alpha vs SPY for each instance?
- Were there any decisions that all 3 instances made differently? What happened?

## Step 3: Thesis Health Review

For EACH active thesis, evaluate:
1. Current conviction and conviction velocity (trend in recent updates)
2. Prediction accuracy (from belief updater data)
3. Position P&L
4. Any cross-reference alerts (insider selling, regulatory ceiling)
5. Any auto-corrections applied this week

```python
PYTHONPATH=. python3 -c "
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
from datetime import datetime, timedelta
import json

tracker = ThesisTracker(paths.theses)
theses = tracker.get_all_theses()

# Load corrections for cross-reference
corrections_log = paths.logs / 'auto_corrections.jsonl'
week_corrections = []
if corrections_log.exists():
    cutoff = datetime.now() - timedelta(days=7)
    for line in open(corrections_log):
        try:
            entry = json.loads(line.strip())
            ts = datetime.fromisoformat(entry.get('timestamp',''))
            if ts >= cutoff:
                week_corrections.append(entry)
        except (json.JSONDecodeError, ValueError):
            pass

# Load prediction accuracy from latest belief update
intel_dir = paths.intelligence
daily_updates = sorted(intel_dir.glob('daily_update_*.json'), reverse=True)
thesis_accuracy = {}
if daily_updates:
    with open(daily_updates[0]) as f:
        report = json.load(f)
    for s in report.get('thesis_suggestions', []):
        thesis_accuracy[s['thesis_id']] = {
            'accuracy': s.get('prediction_accuracy', None),
            'count': s.get('prediction_count', 0),
            'suggested_change': s.get('suggested_change', 0),
        }

print('=== THESIS HEALTH REVIEW ===')
for t in sorted(theses, key=lambda x: -x.conviction):
    if t.status != 'active':
        continue

    # Conviction velocity (last 5 updates)
    velocity = 0
    if len(t.conviction_history) >= 2:
        recent = t.conviction_history[-5:]
        velocity = recent[-1].new_value - recent[0].old_value

    # Corrections this week
    thesis_corrections = [c for c in week_corrections if c.get('thesis_id') == t.id]

    # Prediction accuracy
    acc = thesis_accuracy.get(t.id, {})

    print(f'\\n{t.name} (id={t.id})')
    print(f'  Conviction: {t.conviction:.0f}% (velocity: {velocity:+.0f})')
    print(f'  Positions: {t.positions[:6]}')
    print(f'  Predictions: {acc.get(\"count\",0)} total, accuracy={acc.get(\"accuracy\",\"?\")}'[:60])
    print(f'  Auto-corrections this week: {len(thesis_corrections)}')
    for c in thesis_corrections:
        print(f'    [{c[\"action_type\"]}] {c[\"reason\"][:60]}')
    if velocity < -10:
        print(f'  WARNING: Conviction declining rapidly ({velocity:+.0f})')
    if acc.get('accuracy') is not None and acc['accuracy'] < 0.3 and acc.get('count', 0) >= 5:
        print(f'  WARNING: Low prediction accuracy ({acc[\"accuracy\"]:.0%})')
"
```

Decision for each thesis:
- **CONFIRM** (conviction unchanged)
- **ADJUST** (change conviction with specific reason)
- **INVESTIGATE** (flag for deeper research)
- **INVALIDATE** (conviction -> 15%, queue position closure)

Apply conviction changes via ThesisTracker:
```python
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
tracker = ThesisTracker(paths.theses)
thesis = tracker.get_thesis("<id>")
thesis.update_conviction(<new_value>, "[SYSTEM REVIEW] <reason>")
tracker._save_thesis(thesis)
```

## Step 4: Strategy Parameter Review

Check if any thresholds need adjustment:
```python
PYTHONPATH=. python3 -c "
from src.core.paths import paths
import json

# Stress test scenario accuracy (did any scenario prediction miss badly?)
risk_dir = paths.risk_reports
reports = sorted(risk_dir.glob('stress_test_*.json'), reverse=True)
if reports:
    with open(reports[0]) as f:
        st = json.load(f)
    print('Latest stress test:')
    print(f'  VaR95: {st.get(\"var_95_pct\",0):.1f}%')
    print(f'  Concentration: {st.get(\"concentration_risk_score\",0):.2f}')
    print(f'  Max position: {st.get(\"max_single_position_pct\",0):.1f}%')
    print(f'  Max sector: {st.get(\"max_single_sector_exposure_pct\",0):.1f}%')
    print(f'  Recommendations: {st.get(\"recommendations\",[])}')

# Auto-correction cooldown effectiveness
corrections_log = paths.logs / 'auto_corrections.jsonl'
if corrections_log.exists():
    cooldown_hits = 0
    total = 0
    for line in open(corrections_log):
        try:
            entry = json.loads(line.strip())
            total += 1
            if not entry.get('applied'):
                cooldown_hits += 1
        except (json.JSONDecodeError, ValueError):
            pass
    print(f'\\nCorrection cooldown: {cooldown_hits}/{total} blocked ({cooldown_hits/max(total,1):.0%})')

# Check trim queue
trim_queue = paths.scheduler / 'trim_queue.json'
if trim_queue.exists():
    with open(trim_queue) as f:
        trims = json.load(f)
    print(f'\\nPending trims: {len(trims)}')
    for t in trims:
        print(f'  {t[\"symbol\"]}: {t[\"reason\"][:60]}')
"
```

Evaluate these parameters:
- **Gold concentration cap (15%)** -- too tight? too loose given current gold thesis?
- **Auto-correction cooldown (24h)** -- are corrections getting blocked that should apply?
- **Ensemble consensus threshold (2/3)** -- should it be 3/3 for large positions?
- **Position sizing rules** -- any position breaches this week?

Log parameter change recommendations (do NOT change code -- log to strategic context).

## Step 4b: Autonomous Code Upgrades

Based on findings from Steps 1-4, determine if any code changes would improve the system.

**What you CAN change (Tier 1 -- direct modification):**
- Stress test scenario parameters (shock values, probability labels)
- Signal thresholds (conviction velocity pp/day, crisis alpha VIX threshold, RSI thresholds)
- Rules engine limits (concentration caps, stop loss percentages)
- CLAUDE.md documentation updates
- RSS feed URLs in expanded_news.py

**What you CAN create (Tier 2 -- new files in standard locations):**
- New data source modules in `src/data/sources/alternative/`
- New signal generators in `src/signals/`
- New intelligence modules in `src/intelligence/`
- Skill instruction updates in `.claude/skills/`

**What you CANNOT change (Forbidden):**
- `src/upgrades/` (the upgrade system itself)
- `config/credentials*.yaml` (security)
- `scripts/auto_corrections.py` (core safety loop)
- `src/execution/order_manager.py` (trade execution safety)
- `src/core/instance.py` and `src/core/paths.py` (infrastructure)

**Workflow:**
```python
from src.upgrades.auto_upgrader import AutoUpgrader, UpgradeProposal
from datetime import datetime

upgrader = AutoUpgrader()

# 1. Create proposal
proposal = UpgradeProposal(
    id=f"upgrade_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    timestamp=datetime.now().isoformat(),
    tier=1,  # or 2
    category="threshold",  # or "data_source", "signal", "rule", "skill", "evaluation"
    description="Recalibrate gold shock in ceasefire scenario from -12% to -15%",
    files_to_modify=["src/risk/stress_tester.py"],
    files_to_create=[],
    rationale="Actual gold drop this week was -10.3%, scenario predicted -12%. Widening to -15% for safety margin.",
    evidence="GLD weekly return: -10.3%. Stress test predicted: -12%. Error: 1.7pp.",
    estimated_impact="More accurate risk estimates, earlier alerts on gold concentration",
    risk_level="low",
)

# 2. Validate
is_valid, reason = upgrader.validate_proposal(proposal)
if not is_valid:
    print(f"Proposal rejected: {reason}")
    # Log as Tier 3 for human review
else:
    # 3. Create branch
    result = upgrader.apply_upgrade(proposal)

    # 4. Make the actual code changes HERE
    # (edit files using normal Claude Code tools)

    # 5. Finalize (test + merge or rollback)
    result = upgrader.finalize_upgrade(result)
    print(f"Upgrade {'merged' if result.merged else 'rolled back'}: {result.validation_output}")
```

**Rules for upgrades:**
- Maximum 2 upgrades per system-review session
- Always explain the evidence (data, not intuition)
- Tier 1 changes should be small (< 20 lines changed)
- Tier 2 new files should follow existing patterns exactly
- If unsure, log as Tier 3 proposal instead of implementing
- NEVER modify evaluation criteria without also updating the evidence threshold that triggers evaluation changes

**Evaluation criteria you CAN adjust (with evidence):**
- Prediction accuracy thresholds (e.g., changing "< 25% accuracy = invalidate" to "< 20%")
- Calibration targets (e.g., adjusting overconfidence threshold from 40% to 35%)
- Signal quality weights in belief_updater.py
- Convergence thresholds in signal_digest.py
- Meta-observer recommendation thresholds (Jaccard overlap, equity spread)

**Evaluation criteria you CANNOT adjust:**
- The requirement that predictions ARE tracked
- The requirement that all instances are compared
- The requirement that the ensemble exists
- The concept of thesis-based investing
- The exit checklist rules
- PDT compliance

## Step 5: New Thesis Opportunities

Review signals that were not acted on:
```python
PYTHONPATH=. python3 -c "
from src.core.paths import paths
import json

# Cross-reference alerts with 'investigate' recommendation
alerts_file = paths.live / 'cross_reference_alerts.json'
if alerts_file.exists():
    with open(alerts_file) as f:
        data = json.load(f)
    investigate = [a for a in data.get('alerts', [])
                   if 'investigate' in a.get('recommended_action', '').lower()]
    print(f'Alerts recommending investigation: {len(investigate)}')
    for a in investigate[:5]:
        print(f'  {a.get(\"title\",\"\")[:70]} -> {a.get(\"recommended_action\",\"\")[:50]}')

# Thesis suggestions not yet created
suggestions_dir = paths.suggestions
if suggestions_dir.exists():
    suggestion_files = sorted(suggestions_dir.glob('*.json'), reverse=True)[:5]
    for sf in suggestion_files:
        with open(sf) as f:
            s = json.load(f)
        status = s.get('status', 'pending')
        if status == 'pending':
            print(f'  Pending suggestion: {s.get(\"name\",\"?\")} (confidence={s.get(\"confidence\",\"?\")})')

# Research queue
rq_path = paths.scheduler / 'research_queue.json'
if rq_path.exists():
    with open(rq_path) as f:
        rq = json.load(f)
    pending = [item for item in rq if item.get('status') == 'pending']
    print(f'\\nResearch queue: {len(pending)} pending items')
    for item in pending[:5]:
        print(f'  {item.get(\"hypothesis\",\"?\")[:70]}')
"
```

If a new thesis opportunity has strong evidence (3+ convergent signals, cross-instance support), create it:
```python
from src.knowledge.thesis_suggester import ThesisSuggester
suggester = ThesisSuggester()
created = suggester.auto_create_from_suggestions()
```

## Step 6: Write System Review Report

Save to `~/quant_results/system_reviews/review_<date>.json`:
```python
PYTHONPATH=. python3 -c "
import json
from datetime import datetime
from src.core.paths import paths

report = {
    'date': datetime.now().strftime('%Y-%m-%d'),
    'period': '<start_date> to <end_date>',  # Fill in
    'instance_performance': {},   # Fill from Step 2
    'thesis_actions': [],         # Fill from Step 3 (CONFIRM/ADJUST/INVESTIGATE/INVALIDATE per thesis)
    'parameter_recommendations': [],  # Fill from Step 4
    'new_opportunities': [],      # Fill from Step 5
    'corrections_applied_this_week': [],  # From auto_corrections.jsonl
    'next_week_focus': [],        # Your strategic priorities for next week
}

review_file = paths.system_reviews / f'review_{datetime.now().strftime(\"%Y%m%d\")}.json'
with open(review_file, 'w') as f:
    json.dump(report, f, indent=2)
print(f'System review saved: {review_file}')
"
```

## Step 7: Update Strategic Context

Push key findings to strategic context for other sessions to consume:
```python
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext

ctx = StrategicContext.load()

# Add patterns discovered from the week's data
# ctx.add_developing_pattern(
#     name='<pattern name>',
#     evidence='<what you observed>',
#     interpretation='<what it means>',
#     affected_theses=['<thesis names>'],
# )

# Update thesis momentum from conviction changes
# ctx.update_thesis_momentum('<thesis name>', <current_conviction>)

# Note any blind spots discovered
# ctx.add_blind_spot('<something we are not tracking but should>')

# Parameter change recommendations (logged here, not applied to code)
# ctx.add_catalyst(
#     catalyst='Parameter review: <recommendation>',
#     expected_impact='<what would change>',
#     timeline='next_week',
#     affected_theses=[],
# )

ctx.save()
print('Strategic context updated')
"
```

## Step 8: Completion Logging

```python
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type='system-review',
    success=True,
    summary='<what you did>',
    key_findings=['<finding 1>', '<finding 2>'],
    symbols=['<symbols affected>'],
)
"
```
