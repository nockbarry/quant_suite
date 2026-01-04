# Trading Guide: Budget Edition

A comprehensive guide for running the quant trading system with small capital ($200-$2,000).

---

## Table of Contents

1. [Overview](#overview)
2. [Requirements](#requirements)
3. [Account Setup](#account-setup)
4. [Configuration](#configuration)
5. [Running the System](#running-the-system)
6. [Understanding Signals](#understanding-signals)
7. [Risk Management](#risk-management)
8. [Monitoring Your Portfolio](#monitoring-your-portfolio)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)

---

## Overview

This trading system is designed for retail traders with limited capital who want to:

- **Avoid the Pattern Day Trader (PDT) rule** by swing trading (2-10 day holds)
- **Use free data sources** (Yahoo Finance, SEC EDGAR, Reddit)
- **Trade fractional shares** via Alpaca
- **Run everything locally** with no cloud costs

### What This System Does

1. Screens for "budget picks" using alternative data (insider buying, Reddit sentiment)
2. Generates daily trading signals from multiple strategies
3. Applies risk limits to protect your capital
4. Executes trades via Alpaca (paper or live)
5. Monitors your portfolio and alerts you to problems
6. Tracks performance with factor attribution

### Expected Performance

| Metric | Target |
|--------|--------|
| Sharpe Ratio | > 0.5 |
| Win Rate | > 55% |
| Max Drawdown | < 15% |
| Trades per Year | 50-200 |
| Holding Period | 2-10 days |

---

## Requirements

### Software

```bash
# Python 3.10+
python --version

# Install dependencies
pip install -r requirements.txt

# Required packages (key ones)
pip install yfinance alpaca-trade-api duckdb pandas numpy
```

### Hardware

- Any modern computer (Linux, macOS, Windows with WSL)
- 4GB RAM minimum
- 10GB disk space for data cache

### Accounts

| Service | Purpose | Cost |
|---------|---------|------|
| [Alpaca](https://alpaca.markets) | Broker (paper + live) | Free |
| [Alpha Vantage](https://alphavantage.co) | Optional: better data | Free tier available |

---

## Account Setup

### Step 1: Create Alpaca Account

1. Go to [alpaca.markets](https://alpaca.markets) and sign up
2. Complete identity verification
3. Get your API keys from the dashboard:
   - **API Key ID**
   - **Secret Key**
   - Note: Paper trading uses different keys than live trading

### Step 2: Configure Credentials

Create a `.env` file in the project root:

```bash
# .env
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets  # Paper trading

# For live trading (when ready):
# ALPACA_BASE_URL=https://api.alpaca.markets
```

Or set environment variables:

```bash
export ALPACA_API_KEY="your_api_key"
export ALPACA_SECRET_KEY="your_secret_key"
export ALPACA_BASE_URL="https://paper-api.alpaca.markets"
```

### Step 3: Verify Connection

```python
from src.execution import AlpacaBroker

broker = AlpacaBroker()
status = await broker.connect()
print(f"Connected: {status.connected}")

account = await broker.get_account()
print(f"Buying power: ${account.buying_power:,.2f}")
```

---

## Configuration

### Position Sizing by Account Size

| Account Size | Max Positions | Position Size | Min Trade |
|--------------|---------------|---------------|-----------|
| $200 | 5 | $40 | $20 |
| $500 | 5-8 | $60-100 | $20 |
| $1,000 | 8 | $125 | $20 |
| $2,000 | 10 | $200 | $20 |

### Risk Limits (Budget Edition)

```python
from src.risk import RiskConfig

config = RiskConfig(
    max_position_pct=0.25,      # 25% max in one stock
    max_sector_pct=0.40,        # 40% max in one sector
    max_drawdown_pct=0.15,      # 15% max drawdown
    daily_loss_limit_pct=0.05,  # 5% max daily loss
)
```

### Orchestrator Configuration

```python
from src.execution import OrchestratorConfig, TradingMode, ScheduleConfig

config = OrchestratorConfig(
    mode=TradingMode.PAPER,  # Start with paper trading!

    # Customize schedule (Eastern Time)
    schedule=ScheduleConfig(
        data_refresh_time="06:30",
        signal_generation_time="07:00",
        order_execution_time="09:35",  # 5 min after market open
        eod_snapshot_time="16:00",
        attribution_time="16:30",
        daily_report_time="17:00",
    ),

    # Position limits
    max_positions=8,
    min_position_size=20.0,
    max_position_pct=0.25,

    # PDT protection
    enable_pdt_protection=True,  # Always True for accounts < $25k
)
```

---

## Running the System

### Quick Start: Paper Trading

```python
import asyncio
from src.execution import run_paper_trading, OrchestratorConfig, TradingMode

async def main():
    config = OrchestratorConfig(
        mode=TradingMode.PAPER,
        symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
        max_positions=5,
    )

    await run_paper_trading(config, days=5)

asyncio.run(main())
```

### Full Daily Cycle

```python
from src.execution import TradingOrchestrator, OrchestratorConfig, TradingMode

async def run_daily():
    config = OrchestratorConfig(
        mode=TradingMode.PAPER,
        symbols=get_budget_picks(),  # From screener
        max_positions=8,
    )

    orchestrator = TradingOrchestrator(config)
    await orchestrator.initialize()

    # Run one complete daily cycle
    report = await orchestrator.run_daily_cycle()

    print(f"Signals generated: {report.signals_generated}")
    print(f"Orders executed: {report.orders_executed}")
    print(f"Portfolio value: ${report.portfolio_value:,.2f}")

    await orchestrator.shutdown()
```

### Scheduled Execution (Recommended)

For automated daily trading, use cron or a task scheduler:

```bash
# crontab -e
# Run at 6:30 AM ET every weekday
30 6 * * 1-5 cd /path/to/quant_suite && python scripts/run_daily.py
```

Example `scripts/run_daily.py`:

```python
#!/usr/bin/env python3
"""Daily trading script."""

import asyncio
import logging
from datetime import datetime

from src.execution import TradingOrchestrator, OrchestratorConfig, TradingMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info(f"Starting daily cycle at {datetime.now()}")

    config = OrchestratorConfig(
        mode=TradingMode.PAPER,  # Change to LIVE when ready
        max_positions=8,
        enable_pdt_protection=True,
    )

    orchestrator = TradingOrchestrator(config)

    try:
        await orchestrator.initialize()
        report = await orchestrator.run_daily_cycle()

        logger.info(f"Daily cycle complete:")
        logger.info(f"  Signals: {report.signals_generated}")
        logger.info(f"  Orders: {report.orders_executed}")
        logger.info(f"  P&L: ${report.daily_pnl:,.2f}")

    except Exception as e:
        logger.error(f"Daily cycle failed: {e}")
        raise
    finally:
        await orchestrator.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Understanding Signals

### Signal Types

| Signal | Meaning | Typical Action |
|--------|---------|----------------|
| `BUY` | Strong bullish signal | Open long position |
| `SELL` | Exit signal | Close existing position |
| `HOLD` | No action needed | Maintain current position |

### Signal Strength

Signals have a strength from -1.0 to +1.0:

- `+0.8 to +1.0`: Very strong buy
- `+0.5 to +0.8`: Moderate buy
- `-0.5 to +0.5`: Neutral (hold)
- `-0.5 to -0.8`: Moderate sell
- `-0.8 to -1.0`: Very strong sell

### What Drives Signals

The system combines multiple factors:

1. **Insider Activity** (30% weight)
   - Net insider buys in last 60 days
   - C-suite transactions weighted higher

2. **Reddit Sentiment** (25% weight)
   - Bullish/bearish ratio from r/wallstreetbets, r/stocks
   - Mention velocity (sudden spikes = caution)

3. **Technical Factors** (25% weight)
   - RSI (relative strength)
   - Price momentum
   - Volume patterns

4. **Fundamentals** (20% weight)
   - Valuation vs sector
   - Earnings surprises
   - Analyst revisions

---

## Risk Management

### PDT Rule Protection

The Pattern Day Trader rule requires $25,000 minimum equity for accounts that execute 4+ day trades in 5 business days.

**This system protects you by:**

1. Enforcing minimum 2-day hold periods
2. Tracking day trade count
3. Warning when approaching the limit
4. Blocking trades that would trigger PDT

```python
from src.execution.pipeline import PDTTracker

tracker = PDTTracker()
if tracker.day_trades_remaining < 2:
    print("Warning: Approaching PDT limit!")
```

### Drawdown Protection

The system monitors drawdown in real-time:

```python
from src.execution import PortfolioMonitor

monitor = PortfolioMonitor(broker)
monitor.add_alert(
    name="max_drawdown",
    condition=lambda s: s.drawdown_pct > 0.10,  # 10%
    level=AlertLevel.WARNING,
)
monitor.add_alert(
    name="critical_drawdown",
    condition=lambda s: s.drawdown_pct > 0.15,  # 15%
    level=AlertLevel.CRITICAL,
)
```

### Daily Loss Limits

Protect against bad days:

```python
monitor.add_alert(
    name="daily_loss",
    condition=lambda s: s.daily_pnl_pct < -0.03,  # -3%
    level=AlertLevel.WARNING,
)
monitor.add_alert(
    name="stop_trading",
    condition=lambda s: s.daily_pnl_pct < -0.05,  # -5%
    level=AlertLevel.CRITICAL,
)
```

### Position Limits

Never put all eggs in one basket:

```python
from src.risk import RiskLimits

limits = RiskLimits(
    max_position_pct=0.25,  # Max 25% in one stock
    max_sector_pct=0.40,    # Max 40% in one sector
    max_positions=8,        # Diversify across 8 names
)
```

---

## Monitoring Your Portfolio

### Console Dashboard

```python
from src.execution import PortfolioMonitor

monitor = PortfolioMonitor(broker)
await monitor.start()

# Prints real-time updates to console
# Portfolio Value: $1,234.56 (+$23.45, +1.94%)
# Positions: 5 | Cash: $234.56 | Day Trades: 1/3
```

### Slack Alerts (Optional)

```python
from src.execution.monitoring import SlackAlertChannel

slack = SlackAlertChannel(webhook_url="https://hooks.slack.com/...")
monitor.add_channel(slack)

# You'll receive alerts like:
# CRITICAL: Drawdown exceeded 15%! Current: 16.2%
```

### Daily Reports

After each trading day:

```python
from src.evaluation.attribution import RollingFactorAnalysis

analysis = RollingFactorAnalysis(window=20)
result = analysis.analyze(returns)

print(f"Alpha: {result.alpha:.2%}")
print(f"Market Beta: {result.betas['market']:.2f}")
print(f"R-squared: {result.r_squared:.2%}")
```

---

## Troubleshooting

### Common Issues

#### "Insufficient buying power"

```
Error: InsufficientFundsError: Order requires $150, available: $45
```

**Solution:** Reduce position size or wait for settled funds.

#### "PDT rule violation"

```
Warning: Cannot execute trade - would trigger PDT rule
```

**Solution:** Wait for the 5-day window to reset or increase hold time.

#### "Market closed"

```
Error: MarketClosedError: Cannot submit order outside market hours
```

**Solution:** This is expected. Orders queue for next market open.

#### "Connection failed"

```
Error: ConnectionError: Failed to connect to Alpaca
```

**Solutions:**
1. Check internet connection
2. Verify API keys in `.env`
3. Check Alpaca status at status.alpaca.markets

### Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or for specific modules:
logging.getLogger("src.execution").setLevel(logging.DEBUG)
```

### Checking System State

```python
from src.execution import TradingOrchestrator

orchestrator = TradingOrchestrator(config)
state = orchestrator.get_state()

print(f"Last data refresh: {state.last_data_refresh}")
print(f"Signals generated today: {state.signals_generated}")
print(f"Orders executed today: {state.orders_executed}")
print(f"Errors: {state.errors}")
```

---

## FAQ

### How much money do I need to start?

You can start with as little as $200, but $500-$1,000 is recommended for better diversification.

### Will I violate the PDT rule?

No, if you keep `enable_pdt_protection=True` (the default). The system enforces 2-day minimum holds and tracks day trades.

### How often should I check on it?

- **Paper trading:** Daily, to learn how the system works
- **Live trading:** At least once daily, review the daily report

### Can I use this with other brokers?

Currently only Alpaca is supported. The broker interface is designed for extensibility, but only Alpaca has been implemented.

### What if the market crashes?

The 15% max drawdown limit will pause trading. The system will:
1. Alert you immediately
2. Stop opening new positions
3. Wait for your manual review

### How do I switch from paper to live trading?

1. Run paper trading for at least 10 consecutive days
2. Review performance and fix any issues
3. Change configuration:

```python
config = OrchestratorConfig(
    mode=TradingMode.LIVE,  # Changed from PAPER
    # ...
)
```

4. Update `.env` with live API keys:

```bash
ALPACA_BASE_URL=https://api.alpaca.markets  # Live URL
```

### How do I add my own strategies?

```python
from src.strategies import Strategy

class MyStrategy(Strategy):
    name = "my_custom_strategy"

    def generate_signals(self, data):
        # Your logic here
        return signals

# Register it
from src.execution import DailySignalPipeline

pipeline = DailySignalPipeline(strategies=[MyStrategy()])
```

---

## Checklist: Before Going Live

- [ ] Paper traded for 10+ days
- [ ] Sharpe ratio > 0.5 on paper trades
- [ ] Max drawdown stayed under 15%
- [ ] All alerts working correctly
- [ ] Reviewed every trade the system made
- [ ] Understand why each trade was taken
- [ ] Comfortable with the risk levels
- [ ] Live API keys are secure (not in git)
- [ ] Daily monitoring routine established

---

## Support

- **Issues:** Open a GitHub issue
- **Logs:** Check `logs/` directory for detailed logs
- **Data:** Cached data is in `data/` and `~/.quant_cache/`

---

*Last updated: January 2026*
