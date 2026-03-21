"""Autonomous Upgrade System.

Allows the weekly system-review session to propose, implement, test,
and deploy code changes. Works on a git branch with automatic rollback
if tests fail.

Safety tiers:
- Tier 1 (auto-apply): Config changes, thresholds, scenario params, weights
- Tier 2 (branch + test): New modules following patterns, rule changes, skill updates
- Tier 3 (propose only): Architecture changes, new dependencies, security

Forbidden files (NEVER modify):
- src/upgrades/ (prevents recursive self-modification of upgrade logic)
- config/credentials*.yaml (security)
- scripts/auto_corrections.py (core safety loop)
- .git/ (version control internals)
"""
