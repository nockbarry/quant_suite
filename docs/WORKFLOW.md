# Trading Workflow Guide

This document describes the optimal workflow for daily trading with Claude Code.

## Quick Start

### One-Time Setup

```bash
# Install cron jobs for automation
./scripts/setup_cron.sh install
```

This sets up:
- **6:00 AM**: Start daemons, run pre-market prep
- **Every 5 min**: Update state.json during market hours
- **5:00 PM**: Stop daemons

### Manual Start (if not using cron)

```bash
# Before market open
./scripts/trading_day.sh start
```

### Start Claude Session

Once infrastructure is running, start Claude with one of these:

```bash
# Option 1: Quick status check
claude "ready for trading"

# Option 2: Full morning briefing
claude "/morning-briefing"

# Option 3: Go straight to decisions
claude "/trade-decision"
```

---

## Architecture

### Background Processes

```
┌─────────────────────────────────────────────────────────────┐
│                    BACKGROUND LAYER                          │
│                   (runs automatically)                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │ Live Daemon  │   │ Pre-Market   │   │ State.json   │    │
│  │ (every 5m)   │──▶│    Prep      │──▶│  (unified)   │    │
│  └──────────────┘   └──────────────┘   └──────────────┘    │
│                                                              │
│  Updates:                                                    │
│  - Portfolio from Alpaca                                     │
│  - Market breadth & regime                                   │
│  - Signals for watchlist                                     │
│  - Thesis status                                             │
│  - Risk metrics                                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     CLAUDE LAYER                             │
│                 (called on-demand)                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Claude reads state.json → Already has:                      │
│  - Current positions & P&L                                   │
│  - Market regime & sentiment                                 │
│  - Pre-aggregated signals                                    │
│  - Active theses                                             │
│  - Recent learnings                                          │
│                                                              │
│  Claude only needs to:                                       │
│  - Search current news (web)                                 │
│  - Apply judgment & adversarial analysis                     │
│  - Make decisions                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Alpaca API ──┐
             │
Market Data ─┼──▶ LiveDaemon ──▶ state.json ──▶ Claude
             │     (5 min)
Thesis Files─┘
```

---

## Daily Schedule

| Time (ET) | What Happens | Who |
|-----------|--------------|-----|
| 6:00 AM | `trading_day.sh start` | Cron |
| 6:00 AM | Pre-market research prep | Cron |
| 6:05 AM | State.json first update | Daemon |
| 6:30 AM | Start Claude: `/morning-briefing` | You |
| 9:30 AM | Market opens | - |
| 9:30-4:00 | State updates every 5 min | Daemon |
| Anytime | `claude "/trade-decision"` | You |
| Anytime | `claude "check positions"` | You |
| 4:00 PM | Market closes | - |
| 4:30 PM | `claude "/eod-review"` | You |
| 5:00 PM | Daemons stop | Cron |

---

## Recommended Claude Prompts

### Morning (Pre-Market)

```
# Full briefing with news search
/morning-briefing

# Or simpler:
"Prepare for market open"
```

### During Trading

```
# Make decisions
/trade-decision

# Quick check
"Check positions"

# Specific query
"How is the Venezuela thesis doing?"

# Execute approved trades
/execute-trades
```

### End of Day

```
# Full review
/eod-review

# Or simpler:
"Run end of day review"
```

---

## Repeatable Process

### The Ideal Session

1. **Before Claude**: Infrastructure already running, state.json fresh

2. **Start Claude with**: `/morning-briefing` or "ready for trading"

3. **Claude automatically**:
   - Reads state.json (instant - no API calls needed)
   - Searches current news (1-2 web searches)
   - Reviews theses and learnings
   - Presents summary and decision candidates

4. **You review**, Claude executes with `/execute-trades`

5. **Throughout day**: Call Claude for checks, it reads fresh state.json

6. **End of day**: `/eod-review` extracts learnings

### What Makes It Repeatable

1. **State.json is the contract** - Same format every time
2. **Skills are the interface** - `/morning-briefing`, `/trade-decision`, `/eod-review`
3. **Learnings persist** - Claude reads previous learnings each session
4. **Theses track progress** - Conviction and signposts update automatically

---

## Commands Reference

### Shell Scripts

```bash
# Start everything
./scripts/trading_day.sh start

# Check status
./scripts/trading_day.sh status

# Force state update now
./scripts/trading_day.sh update

# Stop everything
./scripts/trading_day.sh stop

# Setup cron automation
./scripts/setup_cron.sh install
```

### Claude Skills

| Skill | When to Use |
|-------|-------------|
| `/morning-briefing` | First thing in morning |
| `/trade-decision` | When ready to make decisions |
| `/execute-trades` | After decisions approved |
| `/eod-review` | After market close |
| `/thesis` | Create/review investment theses |
| `/monitor` | Check portfolio health |
| `/critic` | Validate a strategy |

---

## Troubleshooting

### State.json is stale

```bash
./scripts/trading_day.sh update
```

### Daemon not running

```bash
./scripts/trading_day.sh start
```

### Need to restart everything

```bash
./scripts/trading_day.sh stop
sleep 2
./scripts/trading_day.sh start
```

### Check logs

```bash
tail -f ~/quant_results/logs/live_daemon.log
tail -f ~/quant_results/logs/cron.log
```
