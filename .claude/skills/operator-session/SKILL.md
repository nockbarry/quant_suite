---
name: operator-session
description: Enter persistent operator mode for morning trading sessions. Self-monitors at configurable intervals, surfaces alerts, tracks agent completions, and detects signal convergences. Use when you want Claude to act as a trading desk operator.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Task
---

# Operator Session Skill

Transform Claude into a **persistent trading desk operator** that monitors the automated trading system at configurable intervals.

## How It Works

1. Claude enters an operator loop with check cycles
2. At each check, Claude reads state, detects alerts, reviews completions
3. Between checks, Claude waits (configurable interval)
4. Claude surfaces findings, recommends actions, can spawn research agents
5. Session continues until market close or user exit

## Usage

```bash
# Default: 3-minute check intervals
claude "/operator-session"

# Passive mode: 5-minute intervals (quiet days)
claude "/operator-session --passive"

# Active mode: 1-minute intervals (volatile/day trading)
claude "/operator-session --active"

# Custom interval (in minutes)
claude "/operator-session --interval 2"
```

## What Each Check Does

1. **Read unified state** (`~/quant_results/live/state.json`)
2. **Check alerts**: Portfolio drawdown, VIX spikes, position moves
3. **Check signpost triggers**: Thesis signposts that fired
4. **Review agent completions**: Research findings since last check
5. **Detect convergences**: 3+ signals aligned on same symbol
6. **Check data freshness**: Flag stale data sources
7. **Generate action items**: Prioritized recommendations
8. **Log observation** to `~/quant_results/logs/operator_log.jsonl`

## Operator Check Code

```python
from src.monitoring.operator_loop import get_operator_loop

# Get the operator loop instance
loop = get_operator_loop()

# Perform a check
observation = loop.operator_check()

# Display formatted output
print(loop.format_observation(observation))

# Check if urgent attention needed
if observation.has_urgent_items():
    print("URGENT ITEMS REQUIRE ATTENTION")

# Get session summary
print(loop.get_session_summary())
```

## Check Output Example

```
============================================================
OPERATOR CHECK #5 - 09:45:00
============================================================

Market Regime: DEFENSIVE
  ** REGIME CHANGE DETECTED **

--- ALERTS (3) ---
  [!!] Significant Drawdown: Portfolio down -3.2% today (-$3,400)
  [!] Elevated VIX: VIX at 26.5 (+15%)
  [-] AAPL Big Move: AAPL down 5.2% today

--- SIGNPOST TRIGGERS (1) ---
  Venezuela Energy: Oil exports resume (bullish)

--- AGENT COMPLETIONS (2) ---
  [research] Sector rotation analysis... (completed)
  [news] Overnight news summary... (completed)

--- CONVERGENCES (1) ---
  XLE: 4 bullish signals (insider, options, technical, social)

--- ACTION ITEMS (2) ---
  [HIGH] Review Significant Drawdown
         Reason: Portfolio down -3.2% today (-$3,400)
  [MED] Consider adding to Venezuela Energy
         Reason: Bullish signpost triggered: Oil exports resume

--- RESEARCH SUGGESTIONS ---
  - Deep dive on XLE - 4 signals converging
  - Thesis validation: Venezuela Energy after signpost trigger

============================================================
Check completed in 0.15s
```

## Spawning Research Agents

When a check finds something interesting, spawn a research agent:

```python
# Example: Research a convergence
from src.monitoring.operator_loop import get_operator_loop

loop = get_operator_loop()
obs = loop.operator_check()

# If convergences found, spawn research
for conv in obs.convergences:
    symbol = conv.get('symbol')
    print(f"Found convergence on {symbol}, spawning research agent...")
    # Use Task tool to spawn research agent
```

## Configuration Options

| Mode | Interval | Use Case |
|------|----------|----------|
| Default | 3 min | Normal trading day |
| Passive | 5 min | Low volatility, no active positions |
| Active | 1 min | Day trading, volatile markets, large positions |
| Custom | N min | User-specified |

## Session Workflow

```
6:30 AM   /operator-session              # Start session
          [Check #1: Read overnight state]
          [Check #2: Morning briefing data]
          ...
9:30 AM   Market opens - increase vigilance
          [More frequent checks if --active]
          ...
12:00 PM  [Midday check, spawn research if needed]
          ...
4:00 PM   Market closes
          [Final check, summarize session]
          [Exit or continue for after-hours]
```

## Exit Conditions

- User types `/exit` or `quit`
- User presses Ctrl+C
- Market close (optional auto-exit at 4pm ET)
- Session timeout (configurable, default 8 hours)

## Comprehensive Dashboard Integration

The operator session integrates with the comprehensive dashboard that shows EVERYTHING including Claude's own activity:

```bash
# COMPREHENSIVE DASHBOARD - Shows Claude's activity + full system state
PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard

# Watch mode refreshes every 60s
PYTHONPATH=. python -m src.monitoring.comprehensive_dashboard --watch

# The dashboard shows:
# - CLAUDE ACTIVITY: Running agents, recent completions, decisions, action items
# - MARKET THEME: Primary/secondary themes, sector rotation, VIX
# - OPERATIONS: 13 cron jobs with schedules, status, last run times
# - PORTFOLIO: Position-by-position breakdown, thesis exposure
# - LAYER STATUS: Data, Signal, Agent, Research, Execution, Risk health
```

When running as an operator, the comprehensive dashboard shows what YOU (Claude) are doing:
- Currently running agents (research, monitor, etc.)
- Recent agent completions with results
- Decisions made today
- Action items from operator checks
- Research suggestions to explore

## Data Freshness Tracking

Track WHAT each data source returned, not just WHEN:

```python
from src.monitoring.data_freshness_tracker import get_data_freshness

summary = get_data_freshness()
for name, status in summary.sources.items():
    print(f"{name}: {status.status} - {status.top_signal}")
```

## Signal Summary

Get actionable signals from all sources:

```python
from src.monitoring.signal_summary import get_signal_summary

summary = get_signal_summary()
print(f"Regime: {summary.regime}")
print(f"Top signals: {len(summary.top_signals)}")
print(f"Convergences: {len(summary.convergences)}")
```

## Logs and Outputs

| Output | Path |
|--------|------|
| Operator observations | `~/quant_results/logs/operator_log.jsonl` |
| Agent activity | `~/quant_results/logs/agent_activity.jsonl` |
| Market watch log | `~/quant_results/logs/market_watch.log` |
| Unified state | `~/quant_results/live/state.json` |

## Alert Thresholds

| Alert | Warning | Critical |
|-------|---------|----------|
| Daily P&L | -3% | -5% |
| VIX | >25 | >30 |
| Position loss | -10% | -15% |
| Data staleness | >1 hour | >4 hours |

## Autonomous Execution Mode

Claude can execute trades directly during operator sessions with appropriate safety rails.

### Execution Authority Levels

| Level | What Claude Can Do |
|-------|-------------------|
| `FULL` | Execute any trade within risk limits |
| `THESIS_ONLY` | Only trades linked to active theses (default) |
| `APPROVED` | Only stop-loss and signpost exits |
| `NOTIFY` | Log and alert, but don't execute |
| `DISABLED` | Monitoring only, no execution |

### Set Authority at Session Start

```bash
# Start with thesis-only execution (default, safest for active trading)
PYTHONPATH=. python scripts/claude_execute.py authority thesis

# Full authority for active day
PYTHONPATH=. python scripts/claude_execute.py authority full

# Monitoring only
PYTHONPATH=. python scripts/claude_execute.py authority notify
```

### Execute Trades

```bash
# Check if trade is allowed first
PYTHONPATH=. python scripts/claude_execute.py check BUY FCX 5% --thesis copper123

# Execute a trade
PYTHONPATH=. python scripts/claude_execute.py execute BUY FCX 10 --thesis copper123 --reason "Copper squeeze thesis, adding on dip"

# Close a position
PYTHONPATH=. python scripts/claude_execute.py execute CLOSE ERY --reason "Thesis conflict with Venezuela bull"

# Dry run (check but don't execute)
PYTHONPATH=. python scripts/claude_execute.py execute BUY AAPL 5 --dry-run
```

### Safety Rails

The autonomous operator has built-in safety rails:

| Rail | Default | Purpose |
|------|---------|---------|
| Max single trade | 5% | No single trade > 5% of portfolio |
| Max daily trades | 10 | Stop after 10 trades per day |
| Max daily loss | 3% | Stop buying if down 3%+ |
| Max position | 15% | No position > 15% of portfolio |
| Max sector | 40% | No sector > 40% concentration |
| Trading hours | 9-16 ET | Only trade during market hours |

### Session Persistence

Session state persists to `~/quant_results/live/operator_session.json`:

```bash
# View current session
PYTHONPATH=. python scripts/claude_execute.py status

# Add focus area
PYTHONPATH=. python scripts/claude_execute.py focus "Monitor energy concentration"

# Record observation
PYTHONPATH=. python scripts/claude_execute.py observe "Gold breaking out, thesis confirmed"

# Add pending action
PYTHONPATH=. python scripts/claude_execute.py pending --add "Review LEN if breaks -10%" --priority high

# Get handoff context for next session
PYTHONPATH=. python scripts/claude_execute.py handoff
```

### Autonomous Operator Workflow

```python
from src.monitoring.autonomous_operator import (
    get_autonomous_operator,
    start_autonomous_session,
    ExecutionAuthority,
    TradeProposal,
    TradeType,
)

# Start/resume session
session = start_autonomous_session(
    authority=ExecutionAuthority.THESIS_ONLY,
    resume=True,
)

# Check session state
operator = get_autonomous_operator()
print(operator.get_session_summary())

# Propose and check a trade
proposal = TradeProposal(
    symbol="FCX",
    action="BUY",
    size_pct=3.0,
    trade_type=TradeType.THESIS_ADD,
    thesis_id="copper123",
    reasoning="Copper at record highs, thesis validated",
    confidence=0.75,
)

# Get portfolio context
from src.synthesis.state import UnifiedState
from src.core.paths import paths
state = UnifiedState.load(paths.live_state)

allowed, reason = operator.check_trade_allowed(
    proposal,
    portfolio_value=state.portfolio.equity,
    current_positions={p.symbol: p.market_value for p in state.positions},
    daily_pnl_pct=state.portfolio.day_pnl_pct,
)

if allowed:
    # Execute the trade
    result = await operator.execute_trade(proposal, ...)
    print(f"Trade result: {result.message}")
```

### Session Handoff

When context is running low or switching sessions:

```bash
# Generate handoff summary
PYTHONPATH=. python scripts/claude_execute.py handoff

# The next session reads this and continues seamlessly
```

The handoff includes:
- Trades executed this session
- Focus areas and pending actions
- Key observations
- Current authority and safety rails

## Best Practices

1. **Start with THESIS_ONLY authority** - safest for active trading
2. **Review action items immediately** - especially HIGH priority
3. **Execute thesis-aligned trades** - use the tools to check and execute
4. **Record observations** - builds context for handoff
5. **Set focus areas** - helps maintain attention on key items
6. **Use handoff before context limit** - ensures continuity

## Related Skills

- `/morning-briefing` - Pre-market research (run before operator session)
- `/trade-decision` - Make trading decisions based on operator findings
- `/monitor` - Quick system health check (vs continuous operator mode)
- `/eod-review` - End-of-day review (run after operator session)
