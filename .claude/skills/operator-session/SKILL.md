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

## Unified Dashboard Integration

The operator session uses the same data as the unified dashboard:

```bash
# See everything the operator sees in a single view
PYTHONPATH=. python -m src.monitoring.unified_dashboard

# Watch mode refreshes every 30s
PYTHONPATH=. python -m src.monitoring.unified_dashboard --watch
```

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

## Best Practices

1. **Start with default interval** - adjust based on market conditions
2. **Review action items immediately** - especially HIGH priority
3. **Spawn research on convergences** - multiple signals = higher confidence
4. **Update theses on signpost triggers** - keep conviction levels current
5. **Use `/trade-decision` for actual trades** - operator mode is for monitoring

## Related Skills

- `/morning-briefing` - Pre-market research (run before operator session)
- `/trade-decision` - Make trading decisions based on operator findings
- `/monitor` - Quick system health check (vs continuous operator mode)
- `/eod-review` - End-of-day review (run after operator session)
