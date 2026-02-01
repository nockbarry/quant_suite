---
name: swarm-operator
description: Orchestrate multiple specialized agent swarms for autonomous trading. Coordinates trading, research, and modeling agents with stigmergic communication via shared state files.
---

# Swarm Operator Skill

Orchestrate a swarm of specialized agents for autonomous trading decisions.

## Philosophy

This skill implements **swarm intelligence** principles:
1. **Stigmergy**: Agents communicate indirectly via shared files (state.json, theses, signals)
2. **Division of Labor**: Specialized agents handle specific domains
3. **Emergent Behavior**: Collective intelligence from agent interactions
4. **Self-Organization**: Agents decide when to hand off to others

## Available Agent Swarms

### Trading Swarm (Real-time decisions)
| Agent | Purpose | Trigger |
|-------|---------|---------|
| critic-agent | Validate trades before execution | Before any trade |
| monitor-agent | Portfolio health, anomaly detection | Continuous |
| news-analyst-agent | Event-driven signals | News events |

### Research Swarm (Alpha generation)
| Agent | Purpose | Trigger |
|-------|---------|---------|
| research-agent | Strategy discovery & validation | Daily/weekly cycles |
| alpha-discovery-agent | Scan for market inefficiencies | Idle time |
| brainstorm-agent | Feature ideation | Low signal periods |

### Modeling Swarm (Market understanding)
| Agent | Purpose | Trigger |
|-------|---------|---------|
| regime-detector-agent | Market regime classification | Daily open |
| hypothesis-generator-agent | Turn insights to strategies | After research |
| text-research-agent | Sentiment, embeddings | News events |

### Macro Swarm (External factors)
| Agent | Purpose | Trigger |
|-------|---------|---------|
| macro-research-agent | Geopolitical, economic factors | Weekly |
| data-acquisition-agent | Fetch new data sources | On demand |

## Swarm Execution Patterns

### Pattern 1: Morning Swarm (Parallel)
Run at market open to gather intelligence:

```
SPAWN IN PARALLEL:
├── regime-detector-agent → regime.json
├── news-analyst-agent → overnight_news.json
└── monitor-agent → portfolio_health.json

THEN SEQUENTIAL:
└── Trading decision based on swarm outputs
```

### Pattern 2: Research Swarm (Pipeline)
Run during low-activity periods:

```
SEQUENTIAL PIPELINE:
brainstorm-agent
  → hypothesis-generator-agent
    → research-agent
      → critic-agent
```

### Pattern 3: Crisis Swarm (All hands)
When drawdown or volatility spike detected:

```
SPAWN ALL IN PARALLEL:
├── monitor-agent (assess damage)
├── news-analyst-agent (find cause)
├── regime-detector-agent (regime shift?)
└── critic-agent (validate any actions)

WAIT FOR ALL → Synthesize → Act
```

## Stigmergic Communication

Agents communicate via the shared filesystem:

### Writing Signals (leaving pheromones)
```python
# Agent writes its findings
signal = {
    "agent": "alpha-discovery-agent",
    "timestamp": "2026-01-30T10:00:00",
    "symbol": "NVDA",
    "signal_type": "momentum_divergence",
    "confidence": 0.75,
    "details": "RSI divergence with price"
}
# Write to ~/quant_results/live/signals/alpha_20260130.json
```

### Reading Signals (following pheromones)
```python
# Orchestrator reads all recent signals
signals = load_all_signals(max_age_hours=24)
convergences = find_convergences(signals)  # 3+ agents agree
```

## Orchestration Commands

### Full Swarm Cycle
```
You are the swarm orchestrator. Run a full intelligence cycle:

1. PARALLEL: Spawn morning swarm
   - Task(regime-detector-agent, "Classify current market regime")
   - Task(news-analyst-agent, "Analyze overnight news for portfolio symbols")
   - Task(monitor-agent, "Check portfolio health and anomalies")

2. WAIT for all agents to complete

3. SYNTHESIZE: Read all agent outputs from ~/quant_results/live/

4. DECIDE: Based on swarm intelligence, make trading decisions

5. VALIDATE: Task(critic-agent, "Validate proposed decisions")

6. EXECUTE or QUEUE based on critic approval
```

### Research Swarm
```
Run research swarm for new alpha:

1. Task(brainstorm-agent, "Generate 5 new feature ideas for semiconductors")
2. For each promising idea:
   - Task(hypothesis-generator-agent, "Create testable hypothesis")
   - Task(research-agent, "Backtest and validate")
3. Task(critic-agent, "Safety check all findings")
4. Log validated strategies to ~/quant_results/research/
```

### Crisis Response
```
ALERT: Portfolio drawdown exceeds 3%. Activate crisis swarm:

1. PARALLEL (immediate):
   - Task(monitor-agent, "Full portfolio risk assessment")
   - Task(news-analyst-agent, "What's moving markets?")
   - Task(regime-detector-agent, "Has regime changed?")

2. WAIT max 2 minutes

3. SYNTHESIZE crisis assessment

4. DECIDE: Reduce exposure? Hold? Exit positions?

5. ALERT human via Telegram if action recommended
```

## Session Management

### Start Swarm Session
```bash
# In tmux, start orchestrator
tmux new-session -d -s swarm 'cd ~/projects/quant_suite && claude --dangerously-skip-permissions'

# Attach and run
tmux attach -t swarm
# Then: /swarm-operator
```

### Monitor Swarm Activity
```bash
# Watch agent outputs
tail -f ~/quant_results/logs/*.log

# Check recent signals
ls -la ~/quant_results/live/signals/

# View swarm state
cat ~/quant_results/live/state.json | jq '.swarm_activity'
```

## Configuration

### Swarm Weights (agent trust levels)
```yaml
# ~/quant_results/config/swarm_weights.yaml
agent_weights:
  critic-agent: 1.5      # High trust - safety critical
  monitor-agent: 1.2     # High trust - sees real data
  research-agent: 1.0    # Normal
  brainstorm-agent: 0.8  # Lower - speculative

convergence_threshold: 3  # Minimum agents to agree
min_confidence: 0.6       # Minimum signal confidence
```

### Swarm Schedule
```yaml
# ~/quant_results/config/swarm_schedule.yaml
schedules:
  morning_swarm:
    time: "09:00"
    agents: [regime-detector, news-analyst, monitor]

  midday_check:
    time: "12:00"
    agents: [monitor]

  research_swarm:
    time: "14:00"  # Low activity period
    agents: [brainstorm, research]
    condition: "no_pending_trades"

  eod_swarm:
    time: "15:30"
    agents: [monitor, critic]
```

## Output Format

After each swarm cycle, output:

```
SWARM INTELLIGENCE REPORT
═══════════════════════════════════════════════════════════════

AGENTS CONSULTED: 5
SIGNALS GENERATED: 12
CONVERGENCES FOUND: 2

CONVERGENCE 1: NVDA (Bullish)
├── regime-detector: Risk-on regime favors growth
├── alpha-discovery: Momentum divergence detected
└── news-analyst: Positive earnings revision

CONVERGENCE 2: GLD (Bearish short-term)
├── monitor: Position at +50%, consider trim
├── macro-research: Dollar strength headwind
└── regime-detector: Risk-on reduces safe haven demand

RECOMMENDED ACTIONS:
1. ADD NVDA (3% size) - 3 agents agree, thesis aligned
2. TRIM GLD (sell 25%) - Take profits, 3 agents agree

DISSENT: research-agent suggests holding GLD (Fed uncertainty)

SWARM CONFIDENCE: 72%
═══════════════════════════════════════════════════════════════
```

## Integration with Existing Skills

This skill complements:
- `/morning-briefing` - Run morning swarm first, then briefing synthesizes
- `/trade-decision` - Swarm provides inputs, trade-decision makes final call
- `/operator-session` - Can invoke swarm cycles during session

## Best Practices

1. **Don't over-swarm**: Not every decision needs 5 agents
2. **Trust convergence**: When 3+ agents agree, confidence is high
3. **Respect dissent**: Log disagreements for later learning
4. **Time-box agents**: Set max runtime to prevent context bloat
5. **Prune signals**: Archive signals older than 7 days
