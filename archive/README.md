# Archived Scripts

These scripts were archived on 2026-01-11 as part of codebase cleanup.

## Why Archived

### Venezuela monitors (3 scripts)
**Replaced by**: `/thesis` skill with signpost tracking
- `monitor_venezuela_positions.py`
- `monitor_venezuela_news.py`
- `monitor_loop.py`

### Research scripts (5 scripts)
**Replaced by**: `/research` and `/brainstorm` skills
- `advanced_strategy_builder.py`
- `build_and_evaluate_strategies.py`
- `test_research_system.py`
- `test_advanced_features.py`
- `run_experiments.py`

### Specialized validators (3 scripts)
**Consolidated into**: `scripts/validate_strategy.py` with flags
- `validate_lead_lag_strategy.py`
- `validate_commodity_mean_rev.py`
- `validate_options_strategies.py`

### Exploratory scripts (4 scripts)
**Reason**: One-off research, no longer in active use
- `monday_alpha_scan.py`
- `monday_detailed_analysis.py`
- `expand_portfolio.py`
- `generate_venezuela_hypotheses.py`

## To Restore

If needed, move back to scripts/ directory:
```bash
mv archive/scripts/SCRIPT_NAME.py scripts/
```

## Archive Date
2026-01-11
