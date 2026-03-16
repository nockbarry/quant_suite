---
name: promote
description: Promote validated strategies from research to paper or live trading. Use when a strategy has passed all validation checks and is ready for production. Handles the full promotion pipeline including critic validation, config generation, and deployment.
allowed-tools: Read, Bash(PYTHONPATH=*), Glob, Grep, Write, Edit
---

# Strategy Promotion Skill

Promote validated strategies from research to production trading.

## Promotion Pipeline

```
Research → Critic Validation → Paper Trading → Live Trading
   ↓              ↓                  ↓              ↓
 Discover      Safety Check      Test Real-Time   Deploy
```

## Quick Start

```bash
# Scan for promotion candidates
PYTHONPATH=. python -m workflows.promotion.strategy_promoter scan

# List pending promotions
PYTHONPATH=. python -m workflows.promotion.strategy_promoter list

# Promote to paper trading
PYTHONPATH=. python -m workflows.promotion.strategy_promoter promote --target paper

# Promote to live (requires confirmation)
PYTHONPATH=. python -m workflows.promotion.strategy_promoter promote --target live --confirm
```

## Promotion Requirements

### Minimum Criteria

| Requirement | Threshold | Source |
|-------------|-----------|--------|
| MCPT p-value | < 0.05 | `mcpt_test()` |
| Validation Sharpe | > 0.5 | Walk-forward OOS |
| Lookahead bias | None | Critic validation |
| Transaction cost test | Pass at 10bps | Backtest |
| Sharpe CI lower bound | > 0 | Bootstrap |
| Paper trading period | 2+ weeks | Live results |

### Promotion Checklist

```python
def check_promotion_ready(strategy_name, symbol):
    """
    Verify strategy meets all promotion criteria.
    """
    from workflows.research.session_tracker import get_tracker

    tracker = get_tracker()
    experiments = tracker.get_experiment_history(strategy=strategy_name, symbol=symbol)

    if not experiments:
        return False, "No experiment records found"

    latest = experiments[0]

    checks = {
        "has_experiment": bool(latest),
        "result_success": latest.result == "success",
        "sharpe_above_threshold": (latest.sharpe or 0) > 0.5,
        "pvalue_significant": (latest.p_value or 1) < 0.05,
        "critic_passed": True,  # TODO: Check critic report
    }

    all_passed = all(checks.values())
    failed = [k for k, v in checks.items() if not v]

    return all_passed, failed if failed else "All checks passed"
```

## Creating a Strategy Spec

```python
from src.core.strategy_spec import StrategySpec

# From experiment results
spec = StrategySpec.from_experiment(
    strategy_name='bollinger_reversal',
    symbol='QCOM',
    params={'period': 20, 'num_std': 2.0},
    train_sharpe=0.74,
    val_sharpe=3.14,
    p_value=0.008,
    pdt_holding_period=10,
)

# Generate YAML config
yaml_config = spec.to_yaml()
print(yaml_config)
```

## Adding to Production Config

The production config is at `config/strategies/validated_strategies.yaml`:

```yaml
strategies:
  bollinger_reversal_qcom:
    class: BollingerReversalStrategy
    enabled: true
    symbols:
      - QCOM
    params:
      period: 20
      num_std: 2.0
    risk:
      max_position_pct: 0.25
      stop_loss_pct: 0.05
      take_profit_pct: 0.10
      min_holding_days: 10  # PDT compliant
    schedule:
      signal_time: "07:00"
      execute_time: "09:35"
    validation:
      promoted_at: "2026-01-03"
      research_cycle: "cycle_20260103_195257"
      val_sharpe: 3.14
      p_value: 0.008
      critic_approved: true
```

## Full Promotion Workflow

### Step 1: Verify Research Results

```python
import json
from pathlib import Path

def get_latest_research_results():
    results_dir = Path("~/quant_results/comprehensive_research")
    latest = sorted(results_dir.glob("cycle_*.json"))[-1]

    with open(latest) as f:
        return json.load(f)

results = get_latest_research_results()
candidates = [s for s in results['best_strategies'] if s['passes_all_checks']]
```

### Step 2: Run Critic Validation

```python
# Use /critic skill
# Must pass: lookahead, overfitting, timing, costs, significance
```

### Step 3: Generate Promotion Record

```python
from datetime import datetime

promotion_record = {
    "strategy": "bollinger_reversal",
    "symbol": "QCOM",
    "promoted_at": datetime.now().isoformat(),
    "promoted_to": "paper",
    "research_cycle": results['cycle_id'],
    "metrics": {
        "val_sharpe": 3.14,
        "p_value": 0.008,
        "train_sharpe": 0.74,
        "sharpe_ci": [1.37, 4.76]
    },
    "pdt_config": {
        "min_holding_days": 10,
        "optimal_sharpe": 0.94
    },
    "critic_validation": {
        "passed": True,
        "checked_at": datetime.now().isoformat()
    },
    "status": "PAPER_TRADING"
}

# Save promotion record
output_path = Path("~/quant_results/promotions")
output_path.mkdir(exist_ok=True)
with open(output_path / f"promo_{promotion_record['strategy']}_{promotion_record['symbol']}.json", 'w') as f:
    json.dump(promotion_record, f, indent=2)
```

### Step 4: Update Config

```python
import yaml
from pathlib import Path

config_path = Path("config/strategies/validated_strategies.yaml")

with open(config_path) as f:
    config = yaml.safe_load(f)

# Add new strategy
config['strategies']['bollinger_reversal_qcom'] = {
    'class': 'BollingerReversalStrategy',
    'enabled': True,
    'symbols': ['QCOM'],
    'params': {'period': 20, 'num_std': 2.0},
    'risk': {
        'max_position_pct': 0.25,
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.10,
        'min_holding_days': 10
    }
}

with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False)
```

### Step 5: Deploy

```bash
# Paper trading (automatic with config update)
PYTHONPATH=. python scripts/run_daily.py --mode paper

# Live trading (requires manual confirmation)
PYTHONPATH=. python scripts/run_daily.py --mode live
```

## Promotion Status Tracking

| Status | Description |
|--------|-------------|
| RESEARCH | Still in research phase |
| VALIDATED | Passed all checks, ready for promotion |
| PAPER_QUEUED | Waiting for paper deployment |
| PAPER_TRADING | Active in paper trading |
| PAPER_COMPLETE | 2+ weeks of paper results |
| LIVE_QUEUED | Ready for live deployment |
| LIVE_TRADING | Active in live trading |
| SUSPENDED | Temporarily disabled |
| RETIRED | Removed from production |

## Rollback Procedure

If a promoted strategy underperforms:

```python
def rollback_strategy(strategy_name, reason):
    """
    Rollback a strategy from production.
    """
    # 1. Disable in config
    config_path = Path("config/strategies/validated_strategies.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    if strategy_name in config['strategies']:
        config['strategies'][strategy_name]['enabled'] = False
        config['strategies'][strategy_name]['disabled_reason'] = reason
        config['strategies'][strategy_name]['disabled_at'] = datetime.now().isoformat()

    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    # 2. Log rollback
    tracker = get_tracker()
    tracker.log_insight(
        title=f"Strategy rollback: {strategy_name}",
        description=reason,
        category="failure",
        evidence={"strategy": strategy_name, "reason": reason}
    )
```

## Output Locations

| Output | Path |
|--------|------|
| Promotion records | `~/quant_results/promotions/` |
| Strategy configs | `config/strategies/validated_strategies.yaml` |
| Critic reports | `~/quant_results/critic_reports/` |
