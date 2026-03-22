# Archived Systems

These modules are superseded by the scheduler/swarm/session architecture.
Preserved for reference but no longer part of the active trading runtime.

## autonomy_loop/
DB-first autonomy engine (event_loop.py, executor.py, athena_autonomy.py).
Replaced by: cron → session_wrapper → Claude skills → DecisionRecord → ensemble → auto-execute.
The event loop tried to be a standalone trading engine; the scheduler path won.

## agents_legacy/
Prompt/config agent framework (base.py, orchestrator.py, etc.) and runtime agent tools.
Replaced by: Claude Code's built-in Agent tool + .claude/agents/*.md definitions.
These were earlier generations of agent abstraction before Claude Code provided native agent spawning.

## orchestration_legacy/
Research orchestration abstractions (parallel_executor.py, research_cycle.py).
Replaced by: athena_scheduler.sh oneshot sessions and Saturday research cron.

## Current Architecture
See CLAUDE.md for the canonical system architecture.

Primary runtime:
  cron → athena_scheduler.sh → session_wrapper.sh → Claude skills
  → DecisionRecord → run_ensemble.py → cron_auto_execute.py → AlpacaBroker

Control plane: sentinel.py + situation_board.py + strategic_context.py
State: state.json (live) + scheduler JSON (coordination) + SQLite (durable history)
Feedback: prediction_scorer → belief_updater → conviction adjustments
Self-improvement: cross_reference → auto_corrections → system_review → auto_upgrader
