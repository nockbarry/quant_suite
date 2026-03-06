"""Athena Swarm — shared memory and coordination layer.

Provides cross-session context via two shared files:
- situation_board.json: same-day observations, market state, analysis requests
- strategic_context.json: multi-day patterns, thesis momentum, research hypotheses
"""
