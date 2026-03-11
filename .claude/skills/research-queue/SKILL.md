---
name: research-queue
description: Consume research queue tasks — run backtests, validate hypotheses, and log results. Picks highest-priority untested hypothesis and runs it through the evaluation infrastructure.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Research Queue Consumer Skill

Automated research execution session. Reads `research_queue.json` and `strategic_context.json` for untested hypotheses, picks the highest-priority task, runs it through backtesting/validation, and logs results back.

Designed to run Saturday afternoons (2 PM) and can be triggered on-demand.

## Step 1: Load Research Queue and Hypotheses

```bash
PYTHONPATH=. python3 -c "
import json
from pathlib import Path
from src.swarm.strategic_context import StrategicContext

# 1. Read research queue (explicit backtest tasks)
queue_path = Path.home() / 'quant_results' / 'scheduler' / 'research_queue.json'
queue = []
if queue_path.exists():
    with open(queue_path) as f:
        queue = json.load(f)

print(f'=== RESEARCH QUEUE ({len(queue)} tasks) ===')
for i, task in enumerate(queue):
    status = task.get('status', 'pending')
    if status == 'completed':
        continue
    print(f'  [{i}] [{task.get(\"priority\", \"?\")}] {task.get(\"type\", \"?\")} — {task.get(\"description\", \"?\")[:80]}')
    print(f'      symbols: {task.get(\"symbols\", [])}  hypothesis: {task.get(\"hypothesis_id\", \"?\")}')

# 2. Read untested hypotheses from strategic context
ctx = StrategicContext.load()
hypotheses = [h for h in ctx.data.get('research_hypotheses', []) if h.get('status') in ('untested', 'open')]
print(f'\n=== UNTESTED HYPOTHESES ({len(hypotheses)}) ===')
for h in hypotheses:
    print(f'  [{h.get(\"suggested_by\", \"?\")}] {h.get(\"hypothesis\", \"?\")[:80]}')
    if h.get('test_plan'):
        print(f'    test: {h[\"test_plan\"][:60]}')
"
```

## Step 2: Select Task to Execute

Pick the highest-priority task using this priority order:
1. `high` priority queue tasks first
2. Hypotheses suggested by `theorist` (strategic importance)
3. Hypotheses from `internal-review` (system quality)
4. Hypotheses from `hypothesis-gen` or `evening-research`
5. `medium` then `low` priority queue tasks

**Skip** tasks that:
- Have `status: completed` already
- Reference symbols with no price history available
- Duplicate existing completed research

## Step 3: Run the Research

Based on the task type, execute the appropriate research method:

### For `backtest` tasks:

```bash
PYTHONPATH=. python3 << 'PYEOF'
from src.evaluation.backtest.engine import VectorizedBacktest
from src.evaluation.validation.mcpt import MCPTAnalyzer
import json
from pathlib import Path

# Define the strategy to test based on the hypothesis
# (Fill in from the selected task)

symbol = "<SYMBOL>"
strategy_name = "<STRATEGY_NAME>"

# 1. Run backtest
# backtest = VectorizedBacktest(
#     strategy=strategy,
#     symbols=[symbol],
#     start_date="2024-01-01",
#     end_date="2026-02-28",
# )
# results = backtest.run()
# print(f"Sharpe: {results.sharpe_ratio:.2f}")
# print(f"Total return: {results.total_return:.2%}")
# print(f"Max drawdown: {results.max_drawdown:.2%}")
# print(f"Win rate: {results.win_rate:.2%}")

# 2. Run MCPT validation if Sharpe > 0.5
# if results.sharpe_ratio > 0.5:
#     mcpt = MCPTAnalyzer()
#     p_value = mcpt.test(results)
#     print(f"MCPT p-value: {p_value:.4f}")
#     validated = p_value < 0.05
# else:
#     validated = False

PYEOF
```

### For `data_check` tasks:

```bash
PYTHONPATH=. python3 << 'PYEOF'
# Verify a data relationship or correlation
# (Fill in specific checks from hypothesis)

# Example: Check if 3+ signal convergence predicts 5-day returns
# from src.db.database import get_db
# from src.db.models import SignalRecord, PredictionRecord
# ...analyze correlation...
PYEOF
```

### For `monitor` tasks:

Set up a monitoring condition and log it to strategic context for future checking.

## Step 4: Log Results

```bash
PYTHONPATH=. python3 -c "
import json
from pathlib import Path
from datetime import datetime
from src.swarm.strategic_context import StrategicContext

# 1. Update hypothesis status in strategic context
ctx = StrategicContext.load()
for h in ctx.data.get('research_hypotheses', []):
    if h.get('hypothesis') == '<HYPOTHESIS_TEXT>':  # Match by text
        h['status'] = 'tested'  # or 'confirmed' or 'rejected'
        h['finding'] = '<SUMMARY OF RESULTS>'
        h['tested_at'] = datetime.now().isoformat()
        break
ctx.save()

# 2. Update research queue task status
queue_path = Path.home() / 'quant_results' / 'scheduler' / 'research_queue.json'
if queue_path.exists():
    with open(queue_path) as f:
        queue = json.load(f)
    for task in queue:
        if task.get('hypothesis_id') == '<HYPOTHESIS_ID>':
            task['status'] = 'completed'
            task['completed_at'] = datetime.now().isoformat()
            task['result'] = '<SUMMARY>'
            break
    with open(queue_path, 'w') as f:
        json.dump(queue, f, indent=2)

# 3. Save detailed research report
report = {
    'timestamp': datetime.now().isoformat(),
    'hypothesis': '<HYPOTHESIS>',
    'method': '<backtest|data_check|monitor>',
    'symbols': ['<SYMBOLS>'],
    'results': {
        # Fill with actual results
    },
    'conclusion': '<confirmed|rejected|inconclusive>',
    'next_steps': ['<what to do with this finding>'],
}
research_dir = Path.home() / 'quant_results' / 'live' / 'research'
research_dir.mkdir(parents=True, exist_ok=True)
filename = f'queue_result_{datetime.now().strftime(\"%Y%m%d_%H%M\")}.json'
with open(research_dir / filename, 'w') as f:
    json.dump(report, f, indent=2)
print(f'Research result saved to {research_dir / filename}')
"
```

## Step 5: Generate Follow-Up Hypotheses

If the research reveals new patterns or questions, generate follow-up hypotheses:

```bash
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()

# If results suggest a new angle:
# ctx.add_research_hypothesis(
#     hypothesis='<new testable hypothesis based on findings>',
#     suggested_by='research-queue',
#     test_plan='<how to test>',
# )

ctx.save()
"
```

## Step 6: Write Completion

```bash
PYTHONPATH=. python3 -c "
from src.monitoring.autonomous_mode import write_session_completion

write_session_completion(
    session_type='research-queue',
    success=True,
    summary='<1-2 sentences: which hypothesis tested, result, conclusion>',
    key_findings=['<finding 1>', '<finding 2>'],
    symbols=['<symbols tested>'],
)
"
```
