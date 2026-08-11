# Attic — retired scripts

Scripts moved here are intentionally unscheduled and unmaintained. They were
retired rather than left ambiguously unscheduled (the Jun 10 2026 crontab
rewrite silently dropped six engines for a month before anyone noticed —
"unscheduled but present" is how that happens).

- `run_market_reaction.py` (retired 2026-07-05): news-reaction scoring. No
  consumer; MarketReactionScorer output was never read by auto_corrections or
  any session skill.
- `run_signal_engines.py` (retired 2026-07-05): conviction-velocity + crisis-
  alpha signal snapshot to signal_engines.json. No consumer since the opinion
  system replaced signal snapshots in operator context.

To resurrect: move back to scripts/, add a cron entry in setup_cron.sh
emit_auto_entries(), and add an SLO row in readiness_check JOB_SLOS.
