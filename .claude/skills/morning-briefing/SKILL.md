---
name: morning-briefing
description: Generate pre-market research briefing with overnight news, market data, and alternative signals. Run this before market open (6-8am ET) to inform trading decisions. Outputs structured JSON and markdown summary.
allowed-tools: Read, Bash(PYTHONPATH=*), Bash(curl:*), Glob, Grep, Write, WebSearch, WebFetch
---

# Morning Briefing Skill

Pre-market research and intelligence gathering for informed trading decisions.

## Purpose

This skill gathers and synthesizes:
1. **Overnight news** - Market-moving events while you slept
2. **Pre-market data** - Futures, gap direction, volume
3. **Alternative signals** - Congressional trades, prediction markets, inverse Cramer (coming soon)
4. **Portfolio context** - Current positions and risk exposure

## Quick Start

```bash
# Generate full morning briefing
PYTHONPATH=/home/nock/projects/quant_suite python3 << 'EOF'
import asyncio
from datetime import datetime
from src.decision.morning_briefing import MorningBriefingGenerator

async def main():
    generator = MorningBriefingGenerator()
    briefing = await generator.generate()
    briefing.save()
    print(briefing.to_markdown())

asyncio.run(main())
EOF
```

## What to Research

### 1. Overnight Market News

Search for major market-moving events:
- Fed/central bank statements
- Earnings surprises (after hours and pre-market)
- Geopolitical developments
- Economic data releases
- Sector-specific news for current positions

### 2. Pre-Market Price Action

Check pre-market movers and futures:
- S&P 500 futures (ES) direction
- Major index gaps (QQQ, IWM)
- Pre-market movers in your watchlist
- Volume compared to normal

### 3. Current Portfolio Review

Review positions from yesterday:
- Any overnight news affecting holdings
- Pre-market prices for current positions
- Risk exposure by sector

### 4. Alternative Data (Expand Over Time)

As data sources are implemented:
- Congressional trades (STOCK Act filings)
- Prediction market probability shifts
- Inverse Cramer signals
- Insider trading clusters

## Output Format

Save briefings to: `/home/nock/quant_results/briefings/briefing_YYYYMMDD.json`

```json
{
  "date": "2026-01-06",
  "generated_at": "2026-01-06T07:00:00",
  "market_sentiment": "neutral_to_bullish",

  "overnight_news": [
    {
      "headline": "Fed signals patience on rate cuts",
      "source": "Reuters",
      "time": "2026-01-05T22:30:00",
      "symbols_affected": ["SPY", "QQQ", "TLT"],
      "sentiment": "neutral",
      "importance": "high"
    }
  ],

  "pre_market": {
    "sp500_futures": "+0.3%",
    "nasdaq_futures": "+0.4%",
    "vix": 14.5,
    "major_movers": [
      {"symbol": "NVDA", "change": "+2.1%", "reason": "AI chip demand"}
    ]
  },

  "portfolio_exposure": {
    "total_equity": 95888,
    "sector_breakdown": {"energy": 45, "tech": 20, "other": 35},
    "positions_with_news": ["SLB", "HAL"]
  },

  "alternative_signals": {
    "congressional_trades": [],
    "prediction_markets": [],
    "inverse_cramer": []
  },

  "focus_areas": [
    "Venezuela thesis still playing out - monitor SLB, HAL",
    "Fed commentary tomorrow - position accordingly"
  ],

  "risk_warnings": [
    "Heavy energy concentration (45%)",
    "Options expiring this week need attention"
  ]
}
```

## Research Process

When this skill runs, Claude should:

### Step 1: Web Search for Market News
```
Search: "stock market news today [current date]"
Search: "fed interest rates news"
Search: "[sectors in portfolio] sector news"
```

### Step 2: Check Current Positions
```python
# Get portfolio state
from alpaca.trading.client import TradingClient
client = TradingClient(api_key, secret_key, paper=True)
positions = client.get_all_positions()

# List symbols to research
symbols = [p.symbol for p in positions if len(p.symbol) <= 10]
```

### Step 3: Research Each Position
For each major holding:
- Check overnight news
- Note any earnings, analyst actions
- Flag if thesis has changed

### Step 4: Synthesize and Recommend
Based on research:
- Overall market sentiment
- Specific opportunities or risks
- Recommended focus for today

## Integration with Trade Decisions

The briefing output is consumed by `/trade-decision`:

```python
# In trade-decision skill
with open(f"/home/nock/quant_results/briefings/briefing_{today}.json") as f:
    briefing = json.load(f)

# Use briefing context for decisions
market_sentiment = briefing["market_sentiment"]
overnight_news = briefing["overnight_news"]
focus_areas = briefing["focus_areas"]
```

## Schedule

| Time (ET) | Action |
|-----------|--------|
| 6:00 AM | Run morning briefing |
| 6:30 AM | Review briefing output |
| 7:00 AM | Feed to /trade-decision |

## Key Files

| File | Purpose |
|------|---------|
| `/home/nock/quant_results/briefings/` | Saved briefings |
| `/home/nock/quant_results/TRADING_RULES.md` | Trading rules to follow |
| `/home/nock/quant_results/trading_logs/` | Previous session logs |

## Example Session

```
User: /morning-briefing

Claude: I'll generate your pre-market briefing for January 6, 2026.

## Research Summary

### Overnight News
1. **Fed Commentary** - Waller suggests patience on rate cuts
   - Impact: Slightly hawkish, may pressure growth stocks

2. **China Trade** - New tariff concerns emerging
   - Impact: Watch semiconductor supply chain

3. **Energy Sector** - Venezuela stability improving per State Dept
   - Impact: Supports SLB/HAL thesis

### Pre-Market Check
- S&P futures: +0.2%
- Nasdaq futures: +0.3%
- VIX: 14.8 (calm)

### Portfolio Implications
- Energy positions (SLB, HAL, XLE) should benefit from Venezuela news
- No overnight news for other major holdings
- Options expiring Friday need review

### Today's Focus
1. Monitor energy thesis - add on any dip
2. Review Feb options for roll decisions
3. Watch Fed commentary impact

Briefing saved to: /home/nock/quant_results/briefings/briefing_20260106.json
```
