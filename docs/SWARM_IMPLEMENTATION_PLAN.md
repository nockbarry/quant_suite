# Plan: Swarm Architecture — Breaking the Operator Monolith

## Context

The operator is an 8-hour Claude Opus session that does everything: mechanical monitoring (90% of checks), news interpretation (5%), and strategic synthesis (never — runs out of context). It costs ~500K tokens/day, crashes = total blindness, and each restart loses accumulated context.

The fix: a three-layer swarm where Python handles the mechanical, Claude handles the judgment, and shared memory files provide cross-session context.

Reference docs: `docs/SWARM_ARCHITECTURE.md` (design), `docs/SYSTEM_REVIEW.md` (audit findings)

## Architecture

```
Layer 1: SENTINEL (Python, 30s heartbeat, zero Claude tokens)
  → Maintains situation_board.json (same-day shared memory)
  → Triggers Analyst sessions when events need interpretation
  → Replaces health_monitor.py + 90% of operator_loop.py

Layer 2: REACTIVE (Claude, on-demand, 3-10 min)
  → Analyst: interpret events, assess signals (sonnet, triggered)
  → Strategist: enhanced trade-decision (opus, scheduled + triggered)
  → Executor: cron_auto_execute.py (already built)

Layer 3: DEEP (Claude, scheduled + triggered, 10-20 min)
  → Reviewer: enhanced internal-review, maintains strategic_context.json
  → Theorist: weekly strategic thinking, thesis development (new skill)
  → Researcher: event-triggered research (enhanced existing)
```

## Phase 1: Shared Memory Layer

**Goal**: Create situation_board.json and strategic_context.json. All existing sessions read/write them. No new agents yet.

### File 1: `src/swarm/__init__.py` (CREATE, ~5 lines)
```python
"""Athena Swarm — shared memory and coordination layer."""
```

### File 2: `src/swarm/situation_board.py` (CREATE, ~300 lines)

Manages `~/quant_results/scheduler/situation_board.json` — the same-day shared memory.

```python
class SituationBoard:
    """Same-day shared memory read/written by all sessions."""

    BOARD_PATH = Path.home() / "quant_results" / "scheduler" / "situation_board.json"

    @classmethod
    def load(cls) -> "SituationBoard":
        """Load current board, auto-reset if date changed."""

    @classmethod
    def load_or_create(cls) -> "SituationBoard":
        """Load or create fresh board for today."""

    def add_observation(self, source: str, obs_type: str, text: str,
                       symbols: list[str] = None, thesis: str = None,
                       action: str = None):
        """Append an observation to today's board."""

    def add_decision(self, symbol: str, action: str, confidence: float,
                    status: str, reasoning_summary: str):
        """Record a trade decision."""

    def update_market_snapshot(self, state: dict):
        """Update market snapshot from state.json data."""
        # Extract: spy, spy_change, vix, vix_change_1h, regime, sector leaders/laggards

    def update_portfolio_alerts(self, state: dict):
        """Update portfolio alerts from position data."""
        # Flag: stop_approaching (-12%+), big movers (5%+), concentration warnings

    def add_analysis_request(self, trigger: str, context: str):
        """Queue an analysis request for the next Analyst session."""

    def get_pending_analyses(self) -> list[dict]:
        """Get unconsumed analysis requests."""

    def consume_analysis(self, analysis_id: str):
        """Mark an analysis as consumed."""

    def save(self):
        """Write board to disk atomically (write tmp + rename)."""

    def get_summary(self) -> str:
        """One-paragraph summary for Claude session injection."""
```

**Schema** (mirrors `docs/SWARM_ARCHITECTURE.md`):
```json
{
  "date": "2026-03-06",
  "last_updated": "...",
  "market_snapshot": { "spy", "spy_change", "vix", "vix_change_1h", "regime", "sector_leaders", "sector_laggards" },
  "today_observations": [{ "time", "source", "type", "text", "symbols", "thesis", "action" }],
  "active_analyses": [{ "id", "trigger", "status", "context", "requested_at" }],
  "decisions_today": [{ "symbol", "action", "confidence", "status", "reasoning_summary" }],
  "portfolio_alerts": [{ "symbol", "type", "current_pnl", "stop_level", "thesis" }],
  "regime_context": { "current", "vix_trend_5d", "interpretation" }
}
```

**Key patterns to reuse**:
- Atomic write: write to `.tmp` then `os.rename()` (same pattern as `state.json`)
- Auto-reset on date change (check `board["date"] != today`)
- Observation dedup: skip if same source+text within 5 min

### File 3: `src/swarm/strategic_context.py` (CREATE, ~200 lines)

Manages `~/quant_results/scheduler/strategic_context.json` — multi-day persistent memory.

```python
class StrategicContext:
    """Multi-day persistent memory maintained by Reviewer/Theorist."""

    CONTEXT_PATH = Path.home() / "quant_results" / "scheduler" / "strategic_context.json"

    @classmethod
    def load(cls) -> "StrategicContext":
        """Load strategic context (never auto-resets — multi-day)."""

    def update_thesis_momentum(self, thesis_name: str, conviction: float):
        """Track thesis conviction trend (rolling 7-day window)."""

    def add_developing_pattern(self, name: str, evidence: str,
                               interpretation: str, affected_theses: list[str]):
        """Record a developing multi-day pattern."""

    def update_signal_source_trend(self, source: str, hit_rate: float):
        """Update signal source quality trends."""

    def add_catalyst(self, date: str, event: str, affected: list[str],
                    scenario_bull: str, scenario_bear: str):
        """Add upcoming catalyst with scenarios."""

    def add_research_hypothesis(self, hypothesis: str, suggested_by: str,
                                test_plan: str = None):
        """Add a hypothesis for the researcher to test."""

    def add_open_question(self, question: str):
        """Add an open strategic question."""

    def get_summary(self) -> str:
        """Summary for Claude session injection."""

    def save(self):
        """Write to disk atomically."""
```

### File 4: `scripts/session_wrapper.sh` (MODIFY, ~30 lines)

Inject situation board + strategic context reading into all sessions:

```bash
# After building AUTO_PROMPT (line ~366), before launching claude:

# Build swarm context injection
SWARM_CONTEXT=""
if [ -f "$HOME/quant_results/scheduler/situation_board.json" ]; then
    SWARM_CONTEXT=$(PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load()
print(board.get_summary())
" 2>/dev/null || echo "")
fi

STRATEGIC=""
if [ -f "$HOME/quant_results/scheduler/strategic_context.json" ]; then
    STRATEGIC=$(PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
print(ctx.get_summary())
" 2>/dev/null || echo "")
fi

# Append to AUTO_PROMPT
if [ -n "$SWARM_CONTEXT" ]; then
    AUTO_PROMPT="${AUTO_PROMPT} SITUATION BOARD: ${SWARM_CONTEXT}"
fi
if [ -n "$STRATEGIC" ]; then
    AUTO_PROMPT="${AUTO_PROMPT} STRATEGIC CONTEXT: ${STRATEGIC}"
fi
```

Also add post-session observation writing to the cleanup function:
```bash
# In cleanup(), before write_completion:
PYTHONPATH="$PROJECT_DIR" python3 -c "
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load_or_create()
board.add_observation('$SESSION_TYPE', 'session_complete', 'Session $SESSION_TYPE completed')
board.save()
" 2>/dev/null || true
```

**Existing code to reuse**:
- `build_autonomous_prompt()` at line 246 — extend, don't replace
- `cleanup()` at line 214 — add board update before `write_completion()`
- Lock/state patterns already working — don't touch

### Verification (Phase 1)
```bash
# Test situation board
PYTHONPATH=. python3 -c "
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load_or_create()
board.update_market_snapshot({'market': {'spy': 524, 'vix': 22}})
board.add_observation('test', 'info', 'Test observation', symbols=['SPY'])
board.save()
print(board.get_summary())
"

# Test strategic context
PYTHONPATH=. python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
ctx.update_thesis_momentum('Iran War Energy', 95)
ctx.add_catalyst('2026-03-18', 'MU Earnings', ['MU', 'SOXX'], 'HBM raise', 'Inventory build')
ctx.save()
print(ctx.get_summary())
"

# Test session_wrapper injects context
./scripts/session_wrapper.sh internal-review  # Should see "SITUATION BOARD:" in log
grep "SITUATION BOARD" ~/quant_results/logs/claude_internal-review_*.log
```

---

## Phase 2: Sentinel (Replace health_monitor.py)

**Goal**: Python daemon that runs every 30s, maintains situation board, triggers analyst sessions. Replaces health_monitor.py entirely.

### File 5: `scripts/sentinel.py` (CREATE, ~450 lines)

```python
"""Athena Sentinel — Python monitoring daemon, zero Claude tokens.

Replaces health_monitor.py. Runs every 30 seconds during market hours.
Maintains situation_board.json and triggers Analyst sessions.

Usage:
    python3 scripts/sentinel.py              # Run until market close
    python3 scripts/sentinel.py --once       # Single check
    python3 scripts/sentinel.py --interval 15  # Fast mode (high vol)
"""

class Sentinel:
    def __init__(self, interval: int = 30):
        self.interval = interval
        self.board = SituationBoard.load_or_create()
        self.operator = OperatorLoop()  # Reuse existing check methods!
        self.last_vix = None
        self.last_convergences = set()

    def run_check(self) -> dict:
        """Single sentinel check cycle."""
        # 1. Load state and update board market snapshot
        state = self.operator._load_state()
        self.board.update_market_snapshot(state)
        self.board.update_portfolio_alerts(state)

        # 2. Check signals via operator's existing methods
        alerts = self.operator._check_alerts(state)
        signposts = self.operator._check_signposts()
        convergences = self.operator._check_convergences()
        stale_sources = self.operator._check_data_freshness()
        social = self.operator._check_social_signals()

        # 3. Check session health (from health_monitor.py)
        operator_alive = is_operator_alive()
        stale_locks = check_locks()

        # 4. Evaluate trigger rules
        triggers_fired = self._evaluate_triggers(
            alerts, signposts, convergences, social, state
        )

        # 5. Queue analysis requests for fired triggers
        for trigger in triggers_fired:
            self.board.add_analysis_request(
                trigger=trigger["type"],
                context=trigger["context"],
            )

        # 6. Spawn analyst if needed
        if triggers_fired:
            self._spawn_analyst(triggers_fired)

        # 7. Health monitor actions (restart operator, kill hung sessions)
        if not operator_alive and is_market_hours():
            restart_operator()
        for stale in stale_locks:
            kill_hung_session(stale["session_type"], stale.get("pid"), stale["lock_file"])

        # 8. Save board
        self.board.save()

        # 9. Adapt interval based on regime
        self._adapt_interval(state)

        return {"triggers": len(triggers_fired), "alerts": len(alerts)}

    TRIGGER_RULES = {
        "convergence": lambda self, **kw: any(
            c.get("symbol") not in self.last_convergences
            for c in kw["convergences"] if c.get("signal_count", 0) >= 3
        ),
        "signpost_hit": lambda self, **kw: len(kw["signposts"]) > 0,
        "position_alert": lambda self, **kw: any(
            a.level == "critical" and a.source == "position" for a in kw["alerts"]
        ),
        "vix_spike": lambda self, **kw: (
            self.last_vix is not None and
            kw["state"].get("market", {}).get("vix", 0) - self.last_vix > 3
        ),
        "regime_change": lambda self, **kw: self.operator.last_regime != "unknown" and
            kw["state"].get("market", {}).get("rotation_theme") != self.operator.last_regime,
        "urgent_news": lambda self, **kw: any(
            n.get("is_urgent") for n in self._get_new_news()
        ),
    }

    def _adapt_interval(self, state: dict):
        """Regime-adaptive check interval."""
        vix = state.get("market", {}).get("vix", 15)
        if vix > 35:
            self.interval = 10  # Crisis
        elif vix > 25:
            self.interval = 15  # Elevated
        elif vix < 15:
            self.interval = 60  # Low vol
        else:
            self.interval = 30  # Normal

    def _spawn_analyst(self, triggers: list[dict]):
        """Launch analyst session via athena_scheduler.sh."""
        # Check if analyst already running (lock file)
        # Write trigger context to analysis_queue.json
        # subprocess.run(["athena_scheduler.sh", "oneshot", "analyst"])
```

**Key reuse from existing code**:
- `OperatorLoop._check_alerts()` (line 291 of operator_loop.py) — direct import
- `OperatorLoop._check_signposts()` (line 368) — direct import
- `OperatorLoop._check_convergences()` (line 447) — already reads signal_digest.json
- `OperatorLoop._check_data_freshness()` (line 466) — direct import
- `OperatorLoop._check_social_signals()` (line 544) — direct import
- `is_operator_alive()`, `check_locks()`, `restart_operator()`, `kill_hung_session()` from health_monitor.py (lines 89-301) — import or inline
- `check_state_freshness()`, `check_vix()`, `check_trade_triggers()` from health_monitor.py

### File 6: `scripts/athena_scheduler.sh` (MODIFY, ~20 lines)

Add sentinel start/stop commands alongside existing monitor commands:

```bash
# New command: sentinel-start (replaces monitor-start)
cmd_sentinel_start() {
    # Same as cmd_monitor_start but runs sentinel.py instead of health_monitor.py
    _respawn_pane_if_dead "monitor"
    tmux send-keys -t "$TMUX_SESSION:monitor" \
        "cd $PROJECT_DIR && PYTHONPATH=$PROJECT_DIR python3 $SCRIPT_DIR/sentinel.py 2>&1 | tee -a $LOG_FILE" C-m
    _update_scheduler_state "sentinel" "running"
}

# Modify cmd_monitor_start to call sentinel instead
# (backward compatible — "monitor-start" still works)
```

Also add `analyst` to the oneshot session types.

### File 7: `scripts/setup_cron.sh` (MODIFY, ~10 lines)

Replace health_monitor references with sentinel:
```bash
# Change:
#   55 5 * * 1-5 ... health_monitor.py
# To:
#   55 5 * * 1-5 ... sentinel.py
```

Remove operator-start/stop cron entries (sentinel now handles operator lifecycle).

### Verification (Phase 2)
```bash
# Single sentinel check
PYTHONPATH=. python3 scripts/sentinel.py --once
cat ~/quant_results/scheduler/situation_board.json | python3 -m json.tool | head -30

# Verify trigger detection (simulate)
PYTHONPATH=. python3 -c "
from scripts.sentinel import Sentinel
s = Sentinel()
result = s.run_check()
print(f'Triggers fired: {result[\"triggers\"]}')
print(f'Alerts found: {result[\"alerts\"]}')
"

# Verify health monitor functionality preserved
python3 scripts/sentinel.py --once 2>&1 | grep -E "operator|lock|stale"
```

---

## Phase 3: Reactive Agents (Analyst + Enhanced Strategist)

**Goal**: Create Analyst skill (short, event-driven, sonnet). Enhance trade-decision to read situation board.

### File 8: `.claude/skills/analyst/SKILL.md` (CREATE, ~120 lines)

```markdown
---
name: analyst
description: Short event-driven analysis triggered by Sentinel. Reads situation board, assesses events, writes assessment back.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Analyst Skill

Fast event assessment triggered by Sentinel when market events need LLM interpretation.

## Steps

### Step 1: Read Context
- Load situation board: `~/quant_results/scheduler/situation_board.json`
- Load strategic context: `~/quant_results/scheduler/strategic_context.json`
- Read pending analysis requests from `active_analyses` array

### Step 2: Assess Each Request
For each pending analysis:
- Read the trigger type and context
- Cross-reference with today's observations and strategic patterns
- Determine: is this actionable? What does it mean for our theses?
- Consider: could this be noise? What would change my mind?

### Step 3: Write Assessments
For each assessment, update the situation board:
```python
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load()
board.add_observation(
    source="analyst",
    obs_type="assessment",
    text="<your assessment>",
    symbols=["<affected symbols>"],
    action="recommend_trade" | "monitor" | "dismiss",
)
board.consume_analysis("<analysis_id>")
board.save()
```

### Step 4: Flag for Strategist if Actionable
If assessment recommends trade action:
```python
from src.monitoring.autonomous_mode import write_trade_trigger
write_trade_trigger(symbol=..., direction=..., signal_count=...,
                   signals=[...], source="analyst")
```

### Step 5: Write Completion
```python
from src.monitoring.autonomous_mode import write_session_completion
write_session_completion(
    session_type="analyst",
    success=True,
    summary="<assessments made>",
    key_findings=["<key finding 1>", ...],
    symbols=["<symbols analyzed>"],
)
```
```

### File 9: `scripts/session_wrapper.sh` (MODIFY, ~15 lines)

Add analyst to session type configuration:

```bash
# In get_timeout():
analyst)           echo 5 ;;

# In get_model():
analyst)           echo "sonnet" ;;

# In get_skill_prompt():
analyst)           echo "/analyst" ;;

# In is_market_day case: add analyst to market-day-only sessions
morning-briefing|trade-decision|eod-review|operator|analyst)
```

### File 10: `.claude/skills/trade-decision/SKILL.md` (MODIFY, ~10 lines)

Add situation board reading to Step 0 (context gathering):

```markdown
# Add after existing context building steps:

### Step 0b: Read Swarm Context
```python
# Situation board — what happened today so far
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load()
print("=== Today's Observations ===")
for obs in board.data.get("today_observations", [])[-10:]:
    print(f"  [{obs['time']}] {obs['source']}: {obs['text']}")
print(f"\nPending analyses: {len(board.get_pending_analyses())}")
print(f"Decisions today: {len(board.data.get('decisions_today', []))}")

# Strategic context — multi-day patterns
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
print("\n=== Strategic Context ===")
print(ctx.get_summary())
```
```

Also add post-decision board update to the decision step:
```python
# After create_decision():
board = SituationBoard.load()
board.add_decision(symbol, action, confidence, "pending", reasoning_summary)
board.save()
```

### Verification (Phase 3)
```bash
# Test analyst skill directly
./scripts/session_wrapper.sh analyst

# Verify analyst reads and writes board
cat ~/quant_results/scheduler/situation_board.json | python3 -c "
import json, sys
board = json.load(sys.stdin)
analyst_obs = [o for o in board.get('today_observations', []) if o.get('source') == 'analyst']
print(f'Analyst observations: {len(analyst_obs)}')
for o in analyst_obs:
    print(f'  {o[\"text\"][:80]}')
"

# Test trade-decision reads board context
grep "Today.s Observations" ~/quant_results/logs/claude_trade-decision_*.log | tail -3
```

---

## Phase 4: Deep Agents (Enhanced Reviewer + Theorist)

**Goal**: Internal review becomes the Reviewer (maintains strategic context). Add Theorist for weekly strategic thinking.

### File 11: `.claude/skills/internal-review/SKILL.md` (MODIFY, ~60 lines)

Add Step 6: Maintain Strategic Context (between current Step 5 and Step 6):

```python
### Step 6: Update Strategic Context

from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()

# Update thesis momentum from Step 3 findings
for t in theses:
    if t.status == 'active':
        ctx.update_thesis_momentum(t.name, t.conviction)

# Update signal source trends from Step 2 findings
for source_name, source_info in digest_sources.items():
    if 'hit_rate' in source_info:
        ctx.update_signal_source_trend(source_name, source_info['hit_rate'])

# Add any developing patterns found
# (Reviewer interprets: are there multi-day trends in today's observations?)
from src.swarm.situation_board import SituationBoard
board = SituationBoard.load()
observations = board.data.get("today_observations", [])
# Look for recurring symbols, thesis references, escalating signals

# Flag open questions for theorist
if report.get("action_items"):
    for item in report["action_items"]:
        if "investigate" in item.lower() or "research" in item.lower():
            ctx.add_research_hypothesis(item, suggested_by="internal-review")

ctx.save()
```

Renumber existing Step 6 (completion) to Step 7.

### File 12: `.claude/skills/theorist/SKILL.md` (CREATE, ~150 lines)

```markdown
---
name: theorist
description: Weekly strategic thinking — thesis review, blind spot analysis, scenario planning, forward-looking synthesis.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write
---

# Theorist Skill

Strategic thinking agent. Reviews all theses holistically, identifies portfolio blind spots, generates new thesis candidates, and scenario-plans for upcoming catalysts.

## Steps

### Step 1: Load Full Context
- Read strategic_context.json for multi-day patterns and trends
- Read all active theses via ThesisTracker
- Read recent internal review reports
- Read learnings from last 14 days

### Step 2: Thesis Portfolio Review
For each active thesis:
- Is conviction trend rising, stable, or declining?
- Are we positioned in the right vehicles?
- Are there new vehicles we should consider?
- Is position sizing appropriate given conviction?

### Step 3: Blind Spot Analysis
- What sectors/themes are we NOT exposed to?
- Are there obvious risks we're not hedged against?
- What narratives are strengthening that we're ignoring?
- Cross-check against prediction markets and macro data

### Step 4: Scenario Planning
For each upcoming catalyst in strategic_context:
- What's our portfolio P&L in the bull scenario?
- What's our portfolio P&L in the bear scenario?
- Are we positioned correctly for both?
- What trades would we make in each scenario?

### Step 5: Generate Research Hypotheses
Based on observations:
- What patterns deserve quantitative testing?
- What correlations should the researcher verify?
- What backtests would be most informative?

### Step 6: Update Strategic Context
```python
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
# Add developing patterns, catalysts, research hypotheses, open questions
ctx.save()
```

### Step 7: Write Theorist Report
Write to `~/quant_results/reviews/theorist_{date}.json`:
```python
report = {
    "timestamp": "...",
    "thesis_reviews": [...],
    "blind_spots": [...],
    "scenario_analysis": [...],
    "new_hypotheses": [...],
    "strategic_recommendations": [...],
}
```

### Step 8: Write Completion
```python
from src.monitoring.autonomous_mode import write_session_completion
write_session_completion(
    session_type="theorist",
    success=True,
    summary="<summary>",
    key_findings=["<finding 1>", ...],
    symbols=["<symbols affected>"],
)
```
```

### File 13: `scripts/session_wrapper.sh` (MODIFY, ~5 lines)

Add theorist to session type config:

```bash
# In get_timeout():
theorist)          echo 15 ;;

# In get_model():
theorist)          echo "opus" ;;

# In get_skill_prompt():
theorist)          echo "/theorist" ;;
```

### File 14: `scripts/setup_cron.sh` (MODIFY, ~5 lines)

Add theorist to Sunday schedule:
```bash
# Weekly Thesis + Brainstorm + Theorist
0 18 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot thesis
0 19 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot brainstorm
0 20 * * 0 $SCRIPT_DIR/athena_scheduler.sh oneshot theorist
```

### Verification (Phase 4)
```bash
# Test reviewer (enhanced internal-review) updates strategic context
./scripts/session_wrapper.sh internal-review
cat ~/quant_results/scheduler/strategic_context.json | python3 -m json.tool | head -30

# Test theorist skill
./scripts/session_wrapper.sh theorist
cat ~/quant_results/reviews/theorist_*.json | python3 -m json.tool | head -30

# Verify strategic context has thesis momentum
python3 -c "
from src.swarm.strategic_context import StrategicContext
ctx = StrategicContext.load()
for name, m in ctx.data.get('thesis_momentum', {}).items():
    print(f'{name}: {m}')
"
```

---

## File Summary

| # | File | Action | ~Lines | Phase |
|---|------|--------|--------|-------|
| 1 | `src/swarm/__init__.py` | CREATE | 5 | 1 |
| 2 | `src/swarm/situation_board.py` | CREATE | 300 | 1 |
| 3 | `src/swarm/strategic_context.py` | CREATE | 200 | 1 |
| 4 | `scripts/session_wrapper.sh` | MODIFY — inject board/context + post-session update | 30 | 1 |
| 5 | `scripts/sentinel.py` | CREATE | 450 | 2 |
| 6 | `scripts/athena_scheduler.sh` | MODIFY — add sentinel commands | 20 | 2 |
| 7 | `scripts/setup_cron.sh` | MODIFY — sentinel replaces health_monitor | 10 | 2 |
| 8 | `.claude/skills/analyst/SKILL.md` | CREATE | 120 | 3 |
| 9 | `scripts/session_wrapper.sh` | MODIFY — add analyst session type | 15 | 3 |
| 10 | `.claude/skills/trade-decision/SKILL.md` | MODIFY — read board/context | 10 | 3 |
| 11 | `.claude/skills/internal-review/SKILL.md` | MODIFY — add strategic context update | 60 | 4 |
| 12 | `.claude/skills/theorist/SKILL.md` | CREATE | 150 | 4 |
| 13 | `scripts/session_wrapper.sh` | MODIFY — add theorist session type | 5 | 4 |
| 14 | `scripts/setup_cron.sh` | MODIFY — add theorist to Sunday schedule | 5 | 4 |

**Total**: ~1370 lines across 10 unique files (4 create, 6 modify)

---

## What Changes vs Current

| Dimension | Before | After |
|-----------|--------|-------|
| Operator | 8h Opus monolith ($20-35/day) | Eliminated — Sentinel + triggered Analyst |
| Event response | 1-3 min (operator check interval) | 30 sec (Sentinel) + 3 min (Analyst) |
| Cross-session context | None (each session reads files fresh) | situation_board.json + strategic_context.json |
| Multi-day patterns | None (context resets daily) | strategic_context.json (maintained by Reviewer) |
| Forward-looking | Incidental | Systematic (Theorist + catalysts) |
| Token cost | ~500K/day (8h Opus operator) | ~200K/day (many short sessions) |
| Research | Fixed schedule | Event-triggered from analyst/reviewer |
| Self-healing | Internal review reports → nobody reads | Internal review acts + updates strategic context |

---

## End-to-End Verification

### Unit tests (per-phase, shown above)

### Integration test (abbreviated schedule)
```bash
# 1. Install everything
./scripts/setup_cron.sh install_all

# 2. Start abbreviated test run
./scripts/athena_scheduler.sh setup
python3 scripts/sentinel.py --once  # Single sentinel check
./scripts/athena_scheduler.sh oneshot internal-review  # Reviewer
./scripts/athena_scheduler.sh oneshot analyst  # Analyst (if triggers exist)
./scripts/athena_scheduler.sh oneshot trade-decision  # Strategist

# 3. Verify chain
# Board should have observations from sentinel, analyst, trade-decision
cat ~/quant_results/scheduler/situation_board.json | python3 -m json.tool

# Strategic context should have thesis momentum from reviewer
cat ~/quant_results/scheduler/strategic_context.json | python3 -m json.tool

# Completions should exist for each session
ls -lt ~/quant_results/scheduler/completions/*.json | head -5
```

### Production deployment
```bash
# Install consolidated cron schedule
./scripts/setup_cron.sh install_all

# Start sentinel (replaces health monitor)
./scripts/athena_scheduler.sh setup
./scripts/athena_scheduler.sh sentinel-start

# Verify next morning
./scripts/athena_scheduler.sh status
cat ~/quant_results/scheduler/situation_board.json | python3 -c "
import json, sys
b = json.load(sys.stdin)
print(f'Board date: {b.get(\"date\")}')
print(f'Observations: {len(b.get(\"today_observations\", []))}')
print(f'Last updated: {b.get(\"last_updated\")}')
"
```

### Copy plan to docs
After implementation, copy this plan to `docs/SWARM_IMPLEMENTATION_PLAN.md`.
