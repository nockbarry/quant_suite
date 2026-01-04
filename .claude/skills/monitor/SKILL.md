---
name: monitor
description: Monitor live and paper trading performance. Use when checking portfolio status, reviewing trades, analyzing P&L, detecting anomalies, or evaluating strategy performance in production. Provides real-time dashboards and alerts.
allowed-tools: Read, Bash(PYTHONPATH=*), Bash(curl:*), Glob, Grep, Write
---

# Trading Monitor Skill

Real-time monitoring of paper and live trading performance.

## Quick Start

```bash
# Launch CLI dashboard (uses mock data if no broker connection)
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard --summary

# Quick portfolio check (async - use this pattern)
PYTHONPATH=. python -c "
import asyncio
import yaml

async def check_portfolio():
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

    print(f'Equity: \${float(account.portfolio_value):,.2f}')
    print(f'Cash: \${float(account.cash):,.2f}')
    print(f'Day Trades: {account.day_trade_count}/3')
    print(f'Positions: {len(positions)}')

asyncio.run(check_portfolio())
"

# Use session tracker for quick stats (sync)
PYTHONPATH=. python -c "
from workflows.research.session_tracker import get_tracker
tracker = get_tracker()
summary = tracker.generate_summary_report()
print(f'Insights: {summary[\"totals\"][\"insights\"]}')
print(f'Experiments: {summary[\"totals\"][\"experiments\"]}')
print(f'Successful: {summary[\"totals\"][\"successful_strategies\"]}')
"
```

## Monitoring Components

### 1. Account Status (Async Pattern)

```python
import asyncio
from src.execution.broker.alpaca import AlpacaBroker

async def get_account_status():
    broker = AlpacaBroker(api_key=API_KEY, secret_key=SECRET_KEY, paper=True)
    await broker.connect()

    # Get account info
    account = await broker.get_account()
    print(f"Equity: ${float(account.portfolio_value):,.2f}")
    print(f"Cash: ${float(account.cash):,.2f}")
    print(f"Buying Power: ${float(account.buying_power):,.2f}")
    print(f"Day Trade Count: {account.day_trade_count}/3")

    await broker.disconnect()

asyncio.run(get_account_status())
```

### 2. Position Monitoring

```python
async def check_positions():
    broker = AlpacaBroker(api_key=API_KEY, secret_key=SECRET_KEY, paper=True)
    await broker.connect()

    positions = await broker.get_positions()
    for symbol, pos in positions.items():
        entry = float(pos.entry_price)
        current = float(pos.current_price)
        pnl_pct = (current - entry) / entry * 100
        print(f"{symbol}: {pos.quantity} shares @ ${entry:.2f}")
        print(f"  Current: ${current:.2f} ({pnl_pct:+.1f}%)")
        print(f"  P&L: ${float(pos.unrealized_pnl):,.2f}")

    await broker.disconnect()

asyncio.run(check_positions())
```

### 3. Session Tracker (Sync - Preferred for Research Monitoring)

```python
from workflows.research.session_tracker import get_tracker

tracker = get_tracker()

# Get summary report
summary = tracker.generate_summary_report()
print(f"Total Insights: {summary['totals']['insights']}")
print(f"Total Experiments: {summary['totals']['experiments']}")
print(f"Successful Strategies: {summary['totals']['successful_strategies']}")
print(f"Actionable Insights: {summary['actionable_insights']}")

# Log a new insight
tracker.log_insight(
    title='Strategy performing well',
    description='bollinger_reversal showing consistent gains',
    category='strategy',
    evidence={'sharpe': 2.5},
    tags=['bollinger', 'performance']
)
```

### 4. Strategy Performance Tracking

```python
import json
from pathlib import Path
from datetime import datetime

def get_strategy_performance(strategy_name, days=30):
    """
    Calculate live performance metrics for a strategy.
    """
    results_dir = Path("/home/nock/quant_results/daily_runs")

    trades = []
    for file in sorted(results_dir.glob("*.json"))[-days:]:
        with open(file) as f:
            data = json.load(f)
            strategy_trades = [t for t in data.get('trades', [])
                             if t['strategy'] == strategy_name]
            trades.extend(strategy_trades)

    if not trades:
        return None

    # Calculate metrics
    returns = [t['pnl_pct'] for t in trades if t.get('pnl_pct')]
    total_pnl = sum(t['pnl'] for t in trades if t.get('pnl'))

    import numpy as np
    if returns:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        win_rate = len([r for r in returns if r > 0]) / len(returns)
    else:
        sharpe = 0
        win_rate = 0

    return {
        "strategy": strategy_name,
        "trades": len(trades),
        "total_pnl": total_pnl,
        "sharpe": sharpe,
        "win_rate": win_rate,
        "avg_return": np.mean(returns) if returns else 0
    }
```

### 5. Anomaly Detection

```python
def detect_anomalies(strategy_name, threshold=2.0):
    """
    Detect unusual performance deviations.
    """
    perf = get_strategy_performance(strategy_name, days=90)
    recent = get_strategy_performance(strategy_name, days=7)

    if not perf or not recent:
        return []

    anomalies = []

    # Check: Sharpe degradation
    if perf['sharpe'] > 0 and recent['sharpe'] < perf['sharpe'] * 0.5:
        anomalies.append({
            "type": "SHARPE_DEGRADATION",
            "message": f"Recent Sharpe ({recent['sharpe']:.2f}) < 50% of historical ({perf['sharpe']:.2f})",
            "severity": "HIGH"
        })

    # Check: Win rate drop
    if perf['win_rate'] - recent['win_rate'] > 0.15:
        anomalies.append({
            "type": "WIN_RATE_DROP",
            "message": f"Win rate dropped from {perf['win_rate']:.1%} to {recent['win_rate']:.1%}",
            "severity": "MEDIUM"
        })

    # Check: Drawdown
    # TODO: Implement drawdown tracking

    return anomalies
```

### 6. Daily Summary Report

```python
def generate_daily_summary():
    """
    Generate end-of-day summary.
    """
    broker = AlpacaBroker()
    account = broker.get_account()
    positions = broker.get_positions()
    orders = broker.get_orders(status='filled', after=datetime.now().replace(hour=0))

    summary = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "account": {
            "equity": float(account.equity),
            "cash": float(account.cash),
            "day_trades_used": account.daytrade_count
        },
        "positions": [
            {
                "symbol": p.symbol,
                "qty": int(p.qty),
                "entry": float(p.avg_entry_price),
                "current": float(p.current_price),
                "pnl": float(p.unrealized_pl)
            }
            for p in positions
        ],
        "trades_today": len(orders),
        "total_unrealized_pnl": sum(float(p.unrealized_pl) for p in positions)
    }

    # Save summary
    output_path = Path(f"/home/nock/quant_results/daily_runs/summary_{summary['date']}.json")
    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)

    return summary
```

## Alert Thresholds

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| Drawdown | >5% | >10% | Reduce position size |
| Day Trades | 2/3 used | 3/3 used | Stop day trading |
| Win Rate (7d) | <40% | <30% | Review strategy |
| Daily Loss | >2% | >5% | Halt trading |
| Sharpe (30d) | <0.5 | <0 | Consider removing |

## Dashboard Commands

```bash
# Real-time portfolio dashboard
PYTHONPATH=. python -m src.execution.monitoring.cli_dashboard

# Strategy leaderboard
PYTHONPATH=. python -c "
from src.execution.monitoring.performance import get_strategy_leaderboard
print(get_strategy_leaderboard(days=30))
"

# Check PDT status
PYTHONPATH=. python -c "
from src.execution.broker.alpaca import AlpacaBroker
broker = AlpacaBroker()
account = broker.get_account()
print(f'Day trades used: {account.daytrade_count}/3')
print(f'Can day trade: {account.daytrade_count < 3}')
"
```

## Output Locations

| Output | Path |
|--------|------|
| Daily summaries | `/home/nock/quant_results/daily_runs/summary_*.json` |
| Trade logs | `/home/nock/quant_results/daily_runs/trades_*.json` |
| Performance reports | `/home/nock/quant_results/performance/` |
| Alerts | `/home/nock/quant_results/alerts/` |

## Alpaca API Reference

```python
# Credentials (paper trading)
api_key = "PK7HVRLPGKWQS7S4FTQKHTZA3C"
# See config/credentials.yaml for secret

# Endpoints
# Paper: https://paper-api.alpaca.markets
# Live: https://api.alpaca.markets
```
