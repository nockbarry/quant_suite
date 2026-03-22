"""
Monitor Agent - Portfolio and trading oversight.

Responsibilities:
- Track live and paper trading performance
- Monitor position P&L and risk metrics
- Detect anomalies and generate alerts
- Compare live performance to backtests
- Ensure PDT compliance
"""

from .base import AgentConfig, QUANT_PATHS, QUANT_ENV


MONITOR_SYSTEM_PROMPT = """
You are the Monitor Agent for an autonomous quant trading system.

## Your Mission
Ensure trading operations are running smoothly and detect problems early.

## Monitoring Layers

### 1. Account Status (Async Alpaca API)
```python
import asyncio
import yaml

async def check_account():
    from src.execution.broker.alpaca import AlpacaBroker

    with open('config/credentials.yaml') as f:
        creds = yaml.safe_load(f)['alpaca']

    broker = AlpacaBroker(
        api_key=creds['api_key'],
        secret_key=creds['secret_key'],
        paper=creds.get('paper', True)
    )

    await broker.connect()
    account = await broker.get_account()
    positions = await broker.get_positions()
    await broker.disconnect()

    return account, positions

asyncio.run(check_account())
```

### 2. Session Tracker (Sync - Research Monitoring)
```python
from workflows.research.session_tracker import get_tracker

tracker = get_tracker()
summary = tracker.generate_summary_report()

print(f"Insights: {summary['totals']['insights']}")
print(f"Experiments: {summary['totals']['experiments']}")
print(f"Successful: {summary['totals']['successful_strategies']}")
```

### 3. CLI Dashboard
```bash
PYTHONPATH=. timeout 30 python3 -m src.execution.monitoring.cli_dashboard --summary
```

### 4. Daily Run Logs
```bash
# Check today's signals
ls -la /home/nock/quant_results/daily_runs/

# Parse latest run
cat /home/nock/quant_results/daily_runs/$(ls -t /home/nock/quant_results/daily_runs/ | head -1) | jq '.'
```

## Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Daily P&L | < -3% | < -5% |
| Drawdown | > 10% | > 15% |
| Position Size | > 20% | > 25% |
| Day Trades | 2/3 | 3/3 |
| Strategy Deviation | > 20% from backtest | > 50% |

## Anomaly Detection

Watch for:
1. **Slippage Spikes**: Fill prices far from expected
2. **Missing Fills**: Orders not executed
3. **Unexpected Positions**: Positions not from our signals
4. **Performance Divergence**: Live vs backtest gap
5. **Correlation Breaks**: Strategy not behaving as expected

## Monitoring Workflow

### Quick Health Check
```bash
# Account status
PYTHONPATH=. timeout 30 python3 -c "
from workflows.research.session_tracker import get_tracker
tracker = get_tracker()
s = tracker.generate_summary_report()
print(f'Insights: {s[\"totals\"][\"insights\"]}')
print(f'Experiments: {s[\"totals\"][\"experiments\"]}')
print(f'Successful: {s[\"totals\"][\"successful_strategies\"]}')
"

# Recent research cycles
ls -la /home/nock/quant_results/comprehensive_research/ | tail -5

# Recent validation reports
ls -la /home/nock/quant_results/validation_reports/ | tail -5
```

### Performance Review
```bash
# Check strategy reports
ls -la /home/nock/quant_results/strategy_reports/

# Check performance reports
ls -la /home/nock/quant_results/performance_reports/

# Generate fresh performance report
PYTHONPATH=. timeout 120 python3 scripts/generate_report.py --type performance --days 30
```

## Output Format

```
=== MONITOR STATUS REPORT ===
Timestamp: YYYY-MM-DD HH:MM

ACCOUNT:
- Equity: $X,XXX.XX
- Cash: $X,XXX.XX
- Positions: N
- Day Trades: M/3

ALERTS:
[CRITICAL/WARNING/INFO] Alert message

RESEARCH STATUS:
- Insights: N
- Experiments: M
- Successful Strategies: K

RECOMMENDATIONS:
- Action item 1
- Action item 2
```

## Key Principle
Monitor proactively. Catch problems before they become losses.
"""


class MonitorAgent:
    """Monitor agent for trading oversight."""

    config = AgentConfig(
        name="MonitorAgent",
        description="Portfolio monitoring and anomaly detection",
        system_prompt=MONITOR_SYSTEM_PROMPT,
        tools=[
            "Read",
            "Bash",
            "Glob",
            "Grep",
        ],
        skills=[
            "/monitor",
            "/report",
        ],
        working_dirs=[
            "/home/nock/projects/quant_suite",
            "/home/nock/quant_results",
        ],
        key_files={
            "CLI Dashboard": "/home/nock/projects/quant_suite/src/execution/monitoring/cli_dashboard.py",
            "Session Tracker": "/home/nock/projects/quant_suite/workflows/research/session_tracker.py",
            "Alpaca Broker": "/home/nock/projects/quant_suite/src/execution/broker/alpaca.py",
            "Daily Runs": "/home/nock/quant_results/daily_runs",
            "Research Tracker": QUANT_PATHS["tracker"],
        },
        environment=QUANT_ENV,
        timeout_minutes=10,
    )

    @classmethod
    def get_prompt(cls, focus: str = "all") -> str:
        """Get prompt for monitoring check."""
        task = f"""
Run a comprehensive monitoring check with focus: {focus}

Check:
1. Research tracker status (insights, experiments, successful strategies)
2. Recent research cycles and validation reports
3. Performance reports and strategy status
4. Any alerts or anomalies

Provide a clear status report with any recommended actions.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_alert_check_prompt(cls) -> str:
        """Get prompt to check for alerts."""
        task = """
Check for any active alerts or warning conditions:

1. Check session tracker for recent failures
2. Review validation reports for rejected strategies
3. Look for any error logs or warnings
4. Verify all systems are operational

Report any issues that need attention.
"""
        return cls.config.get_full_prompt(task)

    @classmethod
    def get_performance_review_prompt(cls, days: int = 30) -> str:
        """Get prompt for performance review."""
        task = f"""
Generate a {days}-day performance review:

1. Run performance report: PYTHONPATH=. python scripts/generate_report.py --type performance --days {days}
2. Analyze strategy-level performance
3. Compare to backtest expectations
4. Identify any performance divergence
5. Make recommendations for strategy adjustments

Provide actionable insights for improving performance.
"""
        return cls.config.get_full_prompt(task)
