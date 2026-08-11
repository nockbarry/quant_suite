---
name: internal-review
description: Automated self-assessment of prediction accuracy, signal quality, thesis health, and system diagnostics. Runs 2x daily to catch drift and flag issues.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Internal Review Skill

Automated quality control for the trading system. Checks prediction accuracy, signal quality drift, thesis health, and system diagnostics. Writes a structured review report.

## Steps

### Step 1: Prediction Accuracy Review

Check predictions resolved in the last 7 days:

```bash
PYTHONPATH=. python3 -c "
from src.db.database import get_db, init_db
from src.db.models import PredictionRecord
from datetime import datetime, timedelta
init_db()
cutoff = datetime.now() - timedelta(days=7)
with get_db() as s:
    resolved = s.query(PredictionRecord).filter(
        PredictionRecord.resolved_at >= cutoff,
        PredictionRecord.outcome.isnot(None),
    ).all()
    total = len(resolved)
    correct = sum(1 for p in resolved if p.outcome == 'correct')
    print(f'Last 7 days: {correct}/{total} correct ({correct/total*100:.0f}%)' if total else 'No resolved predictions')
    for p in resolved[-5:]:
        print(f'  {p.symbol} {p.direction} conf={p.confidence:.0%} -> {p.outcome}')
"
```

Compare hit rate to calibration expectations. Flag if hit rate drops below 50% or if high-confidence predictions (>70%) are performing worse than low-confidence ones.

### Step 2: Signal Quality Drift

Check signal quality metrics for drift:

```bash
# Read signal quality tracker data
ls -la ~/quant_results/signal_quality/ 2>/dev/null
cat ~/quant_results/signal_quality/signal_outcomes.json 2>/dev/null | python3 -m json.tool | tail -30

# Check signal digest for source health
cat ~/quant_results/scheduler/signal_digest.json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Signal count: {d.get(\"signal_count\", 0)}')
print(f'Convergences: {d.get(\"convergence_count\", 0)}')
for name, info in d.get('digest_sources', {}).items():
    status = info.get('status', 'unknown')
    age = info.get('age_hours', '?')
    marker = 'STALE' if status == 'stale' else 'OK'
    print(f'  {name}: {marker} ({age}h old)')
"
```

Flag any source whose hit rate dropped >10% from its baseline weight, or any data source that has been stale for >6 hours.

### Step 3: Thesis Health Check

Review all active theses:

```bash
PYTHONPATH=. python3 -c "
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
from datetime import datetime
tracker = ThesisTracker(paths.theses)
theses = tracker.get_all_theses()
for t in theses:
    if t.status != 'active':
        continue
    last_review = t.last_review.strftime('%Y-%m-%d') if t.last_review else 'never'
    last_conv_update = t.conviction_history[-1].timestamp.strftime('%Y-%m-%d') if t.conviction_history else 'never'
    print(f'{t.name}: conviction={t.conviction:.0f}%, last_review={last_review}, last_conviction_update={last_conv_update}')
    if t.conviction < 40:
        print(f'  WARNING: Low conviction ({t.conviction:.0f}%) - will auto-invalidate in Step 3b')
    if t.conviction > 90:
        print(f'  NOTE: Very high conviction ({t.conviction:.0f}%) - verify not anchoring')
"
```

For each thesis: check last signpost evaluation date, days since conviction update, any new contrary evidence from recent briefings.

### Step 3b: Act on Thesis Issues

**Do not just report — fix.** For any issues found in Step 3, take action immediately:

```bash
PYTHONPATH=. python3 -c "
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths
from src.autonomy.provenance import log_event
from datetime import datetime, timedelta

tracker = ThesisTracker(paths.theses)
theses = tracker.get_all_theses()
actions_taken = []

for t in theses:
    if t.status != 'active':
        continue

    # Auto-invalidate theses below 40% conviction (per Trading Rules)
    if t.conviction < 40:
        success = tracker.invalidate_thesis(t.id, f'Auto-invalidated by internal-review: conviction {t.conviction:.0f}% below 40% threshold')
        if success:
            actions_taken.append(f'INVALIDATED {t.name} (conviction={t.conviction:.0f}%)')
            log_event('thesis_auto_invalidated', source='skill:internal-review',
                      severity='warning', title=f'Auto-invalidated: {t.name} ({t.conviction:.0f}%)')

    # Flag anchoring risk for very high conviction (>90%) — log warning, don't auto-act
    elif t.conviction > 90:
        log_event('thesis_anchoring_risk', source='skill:internal-review',
                  severity='info', title=f'High conviction check: {t.name} ({t.conviction:.0f}%) — verify not anchoring')

    # Flag stale theses (no conviction update in 14+ days) — add note, don't invalidate
    if t.conviction_history:
        last_update = t.conviction_history[-1].timestamp
        days_stale = (datetime.now() - last_update).days
        if days_stale >= 14:
            t.add_note(f'[internal-review] No conviction update in {days_stale} days — needs review')
            tracker._save_thesis(t)
            actions_taken.append(f'FLAGGED STALE: {t.name} ({days_stale} days since conviction update)')
            log_event('thesis_stale', source='skill:internal-review',
                      severity='info', title=f'Stale thesis: {t.name} ({days_stale}d without update)')

for a in actions_taken:
    print(f'ACTION TAKEN: {a}')
if not actions_taken:
    print('No automatic actions needed')
"
```

**Rules for auto-action:**
- **conviction < 40%** → Auto-invalidate (per Trading Rules exit checklist)
- **conviction > 90%** → Log warning only (human should verify anchoring)
- **Stale thesis (no update in 14+ days)** → Log warning, add note to thesis asking for review
- All actions are logged to ProcessEvent for audit trail

### Step 3c: Cross-Reference Alerts and Auto-Corrections

Read cross-reference alerts and recent auto-corrections. Push any unacted RED FLAG alerts to the situation board.

```bash
PYTHONPATH=. python3 -c "
from src.core.paths import paths
from src.swarm.situation_board import SituationBoard
from datetime import datetime, timedelta
import json

board = SituationBoard.load_or_create()
alerts_pushed = 0

# 1. Read cross-reference alerts
alerts_file = paths.live / 'cross_reference_alerts.json'
if alerts_file.exists():
    with open(alerts_file) as f:
        data = json.load(f)
    red_flags = [a for a in data.get('alerts', []) if a.get('severity') == 'red_flag']
    warnings = [a for a in data.get('alerts', []) if a.get('severity') == 'warning']
    print(f'Cross-reference alerts: {data.get(\"total_alerts\",0)} total, {len(red_flags)} red flags, {len(warnings)} warnings')

    # Push unacted red flags to situation board
    for alert in red_flags:
        # Check if alert is recent (last 6 hours)
        try:
            alert_time = datetime.fromisoformat(alert.get('timestamp', ''))
            if datetime.now() - alert_time > timedelta(hours=6):
                continue
        except (ValueError, TypeError):
            continue

        board.add_observation(
            source='internal-review',
            obs_type='alert',
            text=f'[RED FLAG] {alert.get(\"title\", \"\")}: {alert.get(\"recommended_action\", \"\")}',
            symbols=alert.get('symbols', []),
        )
        alerts_pushed += 1
        print(f'  PUSHED TO BOARD: {alert.get(\"title\", \"\")}')
else:
    print('No cross-reference alerts file found')

# 1b. Overconfidence red flags (90%+ stated confidence — historically ~33% accurate)
try:
    import sqlite3
    conn = sqlite3.connect(str(paths.base / 'athena.db'))
    cutoff_iso = (datetime.now() - timedelta(hours=24)).isoformat()
    rows = conn.execute(
        \"SELECT symbol, title FROM process_events WHERE event_type='red_flag_overconfidence' AND timestamp >= ?\",
        (cutoff_iso,),
    ).fetchall()
    if rows:
        print(f'\\nOVERCONFIDENCE RED FLAGS (24h): {len(rows)}')
        for sym, title in rows:
            print(f'  {sym}: {title}')
            board.add_observation(
                source='internal-review', obs_type='alert',
                text=f'Overconfidence red flag: {title}',
                symbols=[sym] if sym else [],
            )
            alerts_pushed += 1
except Exception as e:
    print(f'Red-flag query skipped: {e}')

# 2. Read auto-corrections applied since last review
corrections_log = paths.logs / 'auto_corrections.jsonl'
if corrections_log.exists():
    cutoff = datetime.now() - timedelta(hours=12)  # Since last review
    recent_corrections = []
    for line in open(corrections_log):
        try:
            entry = json.loads(line.strip())
            ts = datetime.fromisoformat(entry.get('timestamp', ''))
            if ts >= cutoff and entry.get('applied', False):
                recent_corrections.append(entry)
        except (json.JSONDecodeError, ValueError):
            pass
    print(f'\\nAuto-corrections since last review: {len(recent_corrections)}')
    for c in recent_corrections:
        action = c.get('action_type', '?')
        thesis = c.get('thesis_name', '?')
        reason = c.get('reason', '?')[:60]
        print(f'  [{action}] {thesis}: {reason}')
        if action == 'thesis_invalidate':
            board.add_observation(
                source='internal-review',
                obs_type='alert',
                text=f'Auto-invalidated thesis: {thesis} ({reason})',
                symbols=[c.get('symbol', '')] if c.get('symbol') else [],
            )
            alerts_pushed += 1
else:
    print('No auto-corrections log found')

# 3. Check trim queue
trim_queue = paths.scheduler / 'trim_queue.json'
if trim_queue.exists():
    with open(trim_queue) as f:
        trims = json.load(f)
    if trims:
        print(f'\\nPending trims in queue: {len(trims)}')
        for t in trims:
            print(f'  {t.get(\"symbol\", \"?\")}: {t.get(\"reason\", \"?\")[:60]}')
        board.add_observation(
            source='internal-review',
            obs_type='assessment',
            text=f'{len(trims)} pending trim(s) from auto-corrections — trade-decision should action',
            symbols=[t.get('symbol', '') for t in trims if t.get('symbol')],
        )
        alerts_pushed += 1

board.save()
print(f'\\nTotal alerts pushed to situation board: {alerts_pushed}')
"
```

Include the cross-reference and auto-correction findings in the review report (Step 5).

### Step 4: System Diagnostics

```bash
# State freshness
ls -la ~/quant_results/live/state.json 2>/dev/null
python3 -c "
from pathlib import Path; from datetime import datetime
f = paths.live_state
age_min = (datetime.now().timestamp() - f.stat().st_mtime) / 60 if f.exists() else -1
print(f'state.json age: {age_min:.0f} min' + (' STALE' if age_min > 10 else ' OK'))
"

# Completion record quality (last 5)
ls -t ~/quant_results/scheduler/completions/*.json 2>/dev/null | head -5 | while read f; do
    python3 -c "
import json
with open('$f') as fh:
    r = json.load(fh)
findings = len(r.get('key_findings', []))
symbols = len(r.get('symbols', []))
print(f'{r.get(\"session_type\",\"?\")} @ {r.get(\"completed_at\",\"?\")[:16]}: {findings} findings, {symbols} symbols, source={r.get(\"source\",\"?\")}')
"
done

# Operator uptime today
ls -la ~/quant_results/scheduler/locks/operator.lock 2>/dev/null || echo "Operator not running"

# Decision pipeline
PYTHONPATH=. python3 -c "
from src.db.database import get_db, init_db
from src.db.models import DecisionRecord
from datetime import datetime, timedelta
init_db()
today = datetime.now().replace(hour=0, minute=0, second=0)
with get_db() as s:
    decisions = s.query(DecisionRecord).filter(DecisionRecord.timestamp >= today).all()
    by_status = {}
    for d in decisions:
        by_status[d.status] = by_status.get(d.status, 0) + 1
    print(f'Today: {len(decisions)} decisions')
    for status, count in by_status.items():
        print(f'  {status}: {count}')
    pending = [d for d in decisions if d.status == 'pending']
    if pending:
        print(f'  WARNING: {len(pending)} still PENDING (auto-execute may have failed)')
"
```

### Step 5: Write Review Report

Write findings to `~/quant_results/reviews/internal_review_{date}.json`:

```python
import json
from datetime import datetime
from pathlib import Path

report = {
    "timestamp": datetime.now().isoformat(),
    "prediction_accuracy": {
        "period": "7_days",
        "total": <total>,
        "correct": <correct>,
        "hit_rate": <rate>,
        "issues": [<any flags from step 1>],
    },
    "signal_quality": {
        "total_signals": <count>,
        "convergences": <count>,
        "stale_sources": [<any stale sources>],
        "issues": [<any flags from step 2>],
    },
    "thesis_health": {
        "active_count": <count>,
        "low_conviction": [<theses below 40%>],
        "stale_theses": [<theses not updated in 7+ days>],
        "issues": [<any flags from step 3>],
    },
    "system_health": {
        "state_fresh": <bool>,
        "operator_running": <bool>,
        "pending_decisions": <count>,
        "completion_quality": "<assessment>",
        "issues": [<any flags from step 4>],
    },
    "overall_status": "healthy|warning|critical",
    "action_items": [<prioritized list of things to fix>],
    "actions_taken": [<list of auto-fixes applied in Step 3b>],
    "resolved_items": [<previous action items that were addressed>],
    "unresolved_items": [<previous action items still open>],
    "board_alerts_pushed": <number of alerts pushed to situation board>,
}

reviews_dir = paths.base / "reviews"
reviews_dir.mkdir(parents=True, exist_ok=True)
filename = f"internal_review_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
with open(reviews_dir / filename, "w") as f:
    json.dump(report, f, indent=2)
```

### Step 5b: Check Previous Review Action Items

**Before writing this review, check what action items were flagged last time and whether they were addressed:**

```bash
PYTHONPATH=. python3 -c "
from pathlib import Path
import json
from datetime import datetime

reviews_dir = paths.base / 'reviews'
review_files = sorted(reviews_dir.glob('internal_review_*.json'), key=lambda p: p.name, reverse=True)

if len(review_files) >= 1:
    # Read previous review
    prev_file = review_files[0]  # most recent existing review
    with open(prev_file) as f:
        prev = json.load(f)

    prev_items = prev.get('action_items', [])
    prev_actions = prev.get('actions_taken', [])
    prev_status = prev.get('overall_status', '?')

    print(f'=== PREVIOUS REVIEW ({prev_file.stem}) ===')
    print(f'Status: {prev_status}')

    if prev_items:
        print(f'Action items ({len(prev_items)}):')
        for item in prev_items:
            print(f'  [ ] {item[:80]}')
        print()
        print('Check each item: was it addressed? Flag unresolved items in this review.')

    if prev_actions:
        print(f'Auto-actions taken: {len(prev_actions)}')
        for a in prev_actions:
            print(f'  [x] {a[:80]}')
else:
    print('No previous review found — this is the first run')
"
```

**Track action item resolution:** In Step 5's report, include a `resolved_items` field listing which previous action items were addressed and which remain open. This creates accountability across reviews.

### Step 5c: Push Critical Issues to Situation Board

**If this review finds critical or warning-level issues, push them to the situation board so the operator and trade-decision sessions can see them immediately:**

```bash
PYTHONPATH=. python3 -c "
from src.swarm.situation_board import SituationBoard

board = SituationBoard.load_or_create()

# Push if overall status is 'warning' or 'critical'
# (Fill in based on review findings from Steps 1-4)
#
# board.add_observation(
#     source='internal-review',
#     obs_type='system_alert',
#     text='<critical finding that affects trading decisions>',
#     symbols=[],
# )
#
# Example: prediction accuracy dropped
# board.add_observation(
#     source='internal-review',
#     obs_type='system_alert',
#     text='WARNING: 7-day prediction accuracy dropped to 35% — reduce confidence in new trades',
#     symbols=[],
# )
#
# Example: stale data
# board.add_observation(
#     source='internal-review',
#     obs_type='data_alert',
#     text='STALE: state.json is 45 minutes old — daemon may need restart',
#     symbols=[],
# )

board.save()
"
```

### Step 6: Update Strategic Context

After writing the review report, update the multi-day strategic context with findings from this review. This is how cross-session learning accumulates.

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
from src.swarm.situation_board import SituationBoard
from src.knowledge.thesis import ThesisTracker
from src.core.paths import paths

ctx = StrategicContext.load()

# 1. Update thesis momentum from Step 3 findings
tracker = ThesisTracker(paths.theses)
for t in tracker.get_all_theses():
    if t.status == 'active':
        ctx.update_thesis_momentum(t.name, t.conviction)

# 2. Update signal source trends from Step 2 findings
# (Fill in hit_rate from signal quality data if available)
import json
from pathlib import Path
sq_path = paths.base / 'signal_quality' / 'signal_outcomes.json'
if sq_path.exists():
    with open(sq_path) as f:
        outcomes = json.load(f)
    for source_name, records in outcomes.items():
        if records:
            recent = records[-20:]
            hits = sum(1 for r in recent if r.get('outcome') == 'correct')
            hit_rate = hits / len(recent) if recent else 0.5
            ctx.update_signal_source_trend(source_name, hit_rate)

# 3. Look for developing multi-day patterns in today's observations
board = SituationBoard.load()
observations = board.data.get('today_observations', [])

# Count symbol mentions across observations
from collections import Counter
symbol_counts = Counter()
for obs in observations:
    for sym in obs.get('symbols', []):
        symbol_counts[sym] += 1

# Symbols mentioned 3+ times today may indicate developing patterns
for sym, count in symbol_counts.most_common(5):
    if count >= 3:
        obs_texts = [o['text'][:60] for o in observations if sym in o.get('symbols', [])]
        ctx.add_developing_pattern(
            name=f'{sym} multi-signal day',
            evidence=f'{count} observations today: {obs_texts[0]}...',
            interpretation=f'{sym} saw {count} signals across sources — may indicate developing trend',
            affected_theses=[],
        )

ctx.save()
print('Strategic context updated with thesis momentum + signal trends + patterns')
"
```

If any action items from the review suggest deeper investigation, flag them as research hypotheses:

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()

# Add research hypotheses from action items that suggest investigation
# (Replace these with actual findings from Step 5 report)
action_items = []  # Fill from report['action_items']
for item in action_items:
    lower = item.lower()
    if any(kw in lower for kw in ['investigate', 'research', 'test', 'check why', 'verify']):
        ctx.add_research_hypothesis(
            hypothesis=item,
            suggested_by='internal-review',
            test_plan='Quantitative analysis needed',
        )

ctx.save()
"
```

### Step 7: Market Opinion & Decision Quality Check

Review the Market Opinion System health and cross-instance divergence:

```python
PYTHONPATH=. python3 -c "
from src.db.database import get_db, init_db
from src.db.models import MarketOpinionRecord, DecisionQualityRecord
from datetime import datetime, timedelta
import json
from pathlib import Path

init_db()

# Opinion capture volume
with get_db() as s:
    day_ago = datetime.now() - timedelta(days=1)
    recent_opinions = s.query(MarketOpinionRecord).filter(
        MarketOpinionRecord.created >= day_ago
    ).count()

    scored_opinions = s.query(MarketOpinionRecord).filter(
        MarketOpinionRecord.score_10d_direction.isnot(None)
    ).count()

    print(f'Opinions last 24h: {recent_opinions}')
    print(f'Total scored (10d): {scored_opinions}')

# Decision quality summary
quality_file = Path.home() / 'quant_results/intelligence/decision_quality.json'
if quality_file.exists():
    q = json.loads(quality_file.read_text())
    for h in ('1d', '5d', '10d'):
        d = q.get(h, {})
        if d:
            print(f'Decision quality {h}: {d[\"avg_quality\"]:.0%} correct, alpha={d[\"avg_alpha\"]:+.1f}% (n={d[\"count\"]})')

# Cross-instance opinion divergence
meta_file = Path.home() / 'quant_results/parallel/meta_report_latest.json'
if meta_file.exists():
    meta = json.loads(meta_file.read_text())
    div = meta.get('opinion_divergence', {})
    if div:
        print(f'\\nCross-instance opinion agreement: {div.get(\"avg_direction_agreement\",\"?\"):.0%}')
        high_div = div.get('high_divergence', [])
        if high_div:
            print(f'HIGH DIVERGENCE (instances disagree): {high_div[:5]}')
        high_con = div.get('high_consensus', [])
        if high_con:
            print(f'Full consensus: {high_con[:5]}')
"
```

**Flag if:**
- Opinion capture volume is 0 (sessions not capturing opinions — check skill integration)
- Decision quality avg_quality < 40% at any horizon (decisions worse than random)
- Cross-instance direction agreement < 50% on held positions (high uncertainty)
- Any held position appears in high_divergence list (instances disagree on your position)

For high-divergence held symbols, add an action item: "Review [SYMBOL] — instances disagree on direction. Auto=[dir], Beta=[dir], Gamma=[dir]."

### Step 8: Write Enriched Completion Record

```python
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type="internal-review",
    success=True,
    summary="<overall_status>: <1-2 sentence summary of findings>",
    key_findings=report["action_items"][:5],
    symbols=[],  # No symbols for system review
)
```
