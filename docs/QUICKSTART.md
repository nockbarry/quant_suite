# Project Athena - Quick Start Guide

A 5-minute onboarding guide for new Claude sessions.

---

## First Command

```bash
PYTHONPATH=. python3 scripts/context_dump.py --brief
```

This gives you everything: portfolio, theses, signals, market state.

---

## Key Paths to Know

| What | Path |
|------|------|
| Unified State | `~/quant_results/live/state.json` |
| Active Theses | `~/quant_results/theses/` |
| Trading Rules | `~/quant_results/knowledge/trading_rules.yaml` |
| Decisions | `~/quant_results/decisions/` |
| Skills | `.claude/skills/*/SKILL.md` |
| Agents | `.claude/agents/*.md` |

---

## Skills (Slash Commands)

### Daily Trading
| Command | Purpose |
|---------|---------|
| `/morning-briefing` | Pre-market research and context |
| `/trade-decision` | Generate decisions with adversarial check |
| `/execute-trades` | Execute with human approval |
| `/eod-review` | End-of-day learning extraction |
| `/monitor` | Check portfolio status |

### Research
| Command | Purpose |
|---------|---------|
| `/research` | Run research cycles |
| `/thesis` | Create/review/update theses |
| `/critic` | Safety validation for strategies |

---

## Quick Trade Commands

```bash
# Buy/Sell
PYTHONPATH=. python3 scripts/quick_trade.py buy MU 10
PYTHONPATH=. python3 scripts/quick_trade.py sell SLB 50

# Get quotes
PYTHONPATH=. python3 scripts/quick_trade.py quote MU FCX LEN

# View positions
PYTHONPATH=. python3 scripts/quick_trade.py positions --thesis "Venezuela"

# Close position
PYTHONPATH=. python3 scripts/quick_trade.py close GLD260206C00409000
```

---

## Trading Rules (from 82-trade analysis)

1. **No options** - averaged -14.25% vs stocks +7.75%
2. **Hold positions** - exits averaged -6.66%, holdings +7.75%
3. **Equal weight within theses** - don't concentrate, let winners prove themselves
4. **Max single position**: 15%
5. **Max thesis exposure**: 35%
6. **2-day minimum hold** (PDT compliance for <$25k)

---

## Current System Status

```bash
# Quick health check
PYTHONPATH=. python3 -c "
from src.monitoring import check_all
import asyncio
asyncio.run(check_all())
"

# Data freshness
PYTHONPATH=. python3 -c "
from src.monitoring import get_data_freshness
print(get_data_freshness())
"
```

---

## Agent Types

### Research
- `research-agent` - Full research with logging
- `research-worker-agent` - Parallelizable sector testing
- `alpha-discovery-agent` - Market inefficiency scanning

### Market Intelligence
- `macro-research-agent` - Geopolitical and macro analysis
- `news-analyst-agent` - Event-driven analysis
- `regime-detector-agent` - Market regime classification

### Operations
- `critic-agent` - Safety validation, bias detection
- `monitor-agent` - Portfolio oversight
- `orchestrator-agent` - Multi-agent coordination

---

## Common Patterns

### Read API reference before writing code:
```bash
cat docs/API_QUICK_REF.md
```

### Get broker connection:
```python
from scripts.quick_trade import get_broker
broker = get_broker()
await broker.connect()
```

### Log agent activity:
```python
from src.monitoring import log_agent_start, log_agent_complete
agent_id = log_agent_start("research", "Testing momentum on NVDA")
# ... do work ...
log_agent_complete(agent_id, summary="Found 2 significant strategies", success=True)
```

---

## What Not To Do

1. Don't write boilerplate code - use existing scripts
2. Don't guess API signatures - check `docs/API_QUICK_REF.md`
3. Don't create files unless necessary - prefer editing
4. Don't concentrate positions - equal weight within theses
5. Don't trade options (per trading rules)

---

## Documentation Index

| Need | Read |
|------|------|
| Daily workflow | `docs/WORKFLOW.md` |
| Architecture | `docs/ARCHITECTURE_DIAGRAMS.md` |
| API methods | `docs/API_QUICK_REF.md` |
| Trading patterns | `docs/TRADING_PATTERNS.md` |
| Data sources | `docs/FREE_DATA_SOURCES.md` |
| Research methods | `docs/ALPHA_DISCOVERY.md` |

---

## Start Here

1. Run `scripts/context_dump.py --brief` to see current state
2. Review active theses in `~/quant_results/theses/`
3. Check trading rules in `~/quant_results/knowledge/trading_rules.yaml`
4. Use skills (`/morning-briefing`, `/trade-decision`) not raw code
