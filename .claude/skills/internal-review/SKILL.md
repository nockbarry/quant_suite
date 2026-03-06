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
theses = tracker.list_theses()
for t in theses:
    if t.get('status') != 'active':
        continue
    name = t.get('name', '')
    conv = t.get('conviction', 0)
    updated = t.get('last_updated', 'unknown')
    print(f'{name}: conviction={conv}%, last_updated={updated}')
    # Flag issues
    if conv < 40:
        print(f'  WARNING: Low conviction ({conv}%) - consider invalidating')
    if conv > 90:
        print(f'  NOTE: Very high conviction ({conv}%) - verify not anchoring')
"
```

For each thesis: check last signpost evaluation date, days since conviction update, any new contrary evidence from recent briefings.

### Step 4: System Diagnostics

```bash
# State freshness
ls -la ~/quant_results/live/state.json 2>/dev/null
python3 -c "
from pathlib import Path; from datetime import datetime
f = Path.home() / 'quant_results/live/state.json'
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
}

reviews_dir = Path.home() / "quant_results" / "reviews"
reviews_dir.mkdir(parents=True, exist_ok=True)
filename = f"internal_review_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
with open(reviews_dir / filename, "w") as f:
    json.dump(report, f, indent=2)
```

### Step 6: Write Enriched Completion Record

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
