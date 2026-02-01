# Autonomous Trading Architecture & Agent Framework Analysis

**Date:** February 1, 2026
**Context:** Research session on autonomous trading options, agent frameworks, and swarm intelligence for Project Athena.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Cost Model Analysis](#cost-model-analysis)
3. [Agent Frameworks Evaluated](#agent-frameworks-evaluated)
4. [Swarm Intelligence Architecture](#swarm-intelligence-architecture)
5. [Implementation Details](#implementation-details)
6. [Key Decisions & Tradeoffs](#key-decisions--tradeoffs)
7. [Quick Reference](#quick-reference)

---

## Executive Summary

### The Core Question
How do we build autonomous trading capability that:
- Runs without constant human supervision
- Coordinates multiple specialized agents (trading, research, modeling)
- Provides monitoring and management of agent swarms
- Maximizes the $100/month Claude Max 5x subscription

### The Answer
**Use Claude Code as the swarm orchestrator.** The Max 5x subscription includes unlimited Claude Code usage. The built-in Task tool (subagents) is essentially a swarm orchestration system. We don't need external frameworks or additional API costs.

### Key Insight
```
Claude Code Task tool = Swarm orchestration
Shared filesystem = Stigmergic communication (ant pheromone trails)
Our 13 existing agents = Specialized swarm workers
$100/month flat = All we need
```

---

## Cost Model Analysis

### Critical Clarification

| Approach | Billing Method | Monthly Cost |
|----------|----------------|--------------|
| **Claude Code CLI** | Max 5x subscription | **$100 flat (included)** |
| **Claude Code with --dangerously-skip-permissions** | Max 5x subscription | **$100 flat (included)** |
| **Claude Agent SDK** | API usage (per token) | $100 + ~$150-300 additional |
| **Direct Anthropic API** | API usage (per token) | $100 + ~$60-150 additional |
| **CrewAI / LangChain** | API usage under the hood | $100 + ~$100-200 additional |

### Recommendation
Stay within Claude Code. The Agent SDK and other frameworks use API calls that bill separately from the Max subscription.

### How to Run Autonomously on Max 5x

```bash
# Option 1: tmux session with skip-permissions
tmux new-session -d -s athena 'cd ~/projects/quant_suite && claude --dangerously-skip-permissions'

# Option 2: Cron-triggered Claude Code session
0 9 * * 1-5 tmux new-session -d -s athena \
  'cd ~/projects/quant_suite && claude --dangerously-skip-permissions \
  -p "/swarm-operator morning cycle"'
```

---

## Agent Frameworks Evaluated

### 1. hypercontext.sh / skill.cc

**What it is:** A Claude Code skill for cognitive introspection - lets Claude visualize its own session state (context consumption, thread maps, heat columns).

**Key Concepts:**
- "Reading IS installing" - pure markdown skills, no dependencies
- Skills as decentralized capability registry
- ASCII visualization as first-class information format
- Pylon pattern: same data rendered in multiple lossy views

**URL:** https://hypercontext.sh, https://skill.cc

**Relevance to Us:**
- Interesting for context management during long trading sessions
- Could adopt ASCII cartography for thesis visualization
- Not directly applicable to autonomous trading

**Skills Available:**
- `hypercontext` - Session state visualization
- `cartography` - ASCII map generation

---

### 2. OpenClaw / Moltbot

**What it is:** A local-first personal AI assistant that runs on your machine and connects to multiple messaging channels.

**Key Features:**
- Multi-channel integration (WhatsApp, Telegram, Discord, Slack, iMessage, Signal)
- Multi-agent routing (different agents per channel)
- Voice wake + talk mode
- Live Canvas (visual workspace)
- WebSocket Gateway (ws://127.0.0.1:18789)
- Always-on operation via daemon

**Architecture:**
```
CHANNELS (WhatsApp, Telegram, etc.)
    ↓
GATEWAY (local WebSocket)
    ↓
AGENTS (isolated workspaces)
    ↓
TOOLS (browser, cron, sessions)
```

**URL:** https://github.com/moltbot/moltbot, https://openclaw.ai

**Relevance to Us:**
- Could receive Telegram alerts AND respond to them
- Multi-agent routing is interesting for different trading contexts
- More infrastructure than we need
- Designed for personal assistant, not trading

**Verdict:** Interesting but overkill. Would require significant customization.

---

### 3. Claude Agent SDK

**What it is:** Anthropic's official SDK for building autonomous agents with Claude. Same tools as Claude Code, but programmable in Python/TypeScript.

**Key Features:**
- Built-in tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch
- Subagent support via Task tool
- Session persistence and resumption
- Custom tools via MCP (Model Context Protocol)
- Hooks for permission control (PreToolUse, PostToolUse)
- `permission_mode="bypassPermissions"` for autonomous operation

**Installation:**
```bash
pip install claude-agent-sdk
```

**Basic Usage:**
```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Review state.json and make trading decisions",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Bash", "WebSearch"],
        permission_mode="bypassPermissions"
    )
):
    print(message)
```

**URL:** https://platform.claude.com/docs/en/agent-sdk/overview

**Relevance to Us:**
- Perfect feature set for autonomous trading
- Same tools we already use
- **BUT: Uses API billing, not Max subscription**

**Verdict:** Would be ideal if we wanted to pay for API usage. Since we have Max 5x, Claude Code sessions are more cost-effective.

---

### 4. OpenAI Swarm

**What it is:** Educational framework for lightweight multi-agent orchestration. Explores "agents" and "handoffs" as primitives.

**Key Concepts:**
- **Agents**: Encapsulate instructions and tools
- **Handoffs**: Function returns another Agent → execution transfers
- **Context Variables**: State flows between agents
- Stateless between calls (client-side only)

**Code Example:**
```python
from swarm import Swarm, Agent

def transfer_to_trader():
    return trader_agent

researcher = Agent(
    name="Researcher",
    functions=[transfer_to_trader]
)

trader_agent = Agent(name="Trader")

client = Swarm()
response = client.run(agent=researcher, messages=[...])
```

**URL:** https://github.com/openai/swarm

**Relevance to Us:**
- Lightweight and educational
- Handoff pattern is elegant
- OpenAI-centric (uses their API)
- No built-in persistence

**Verdict:** Good concepts to learn from, but OpenAI-specific.

---

### 5. Swarms Framework (kyegomez)

**What it is:** Enterprise-grade production multi-agent orchestration framework.

**Key Features:**
- Multiple workflow patterns: Sequential, Concurrent, Graph-based, Hierarchical
- Multi-model support (OpenAI, Anthropic, Groq)
- MCP protocol integration
- Memory systems for knowledge retention

**Workflow Patterns:**
```python
from swarms import Agent, SequentialWorkflow, ConcurrentWorkflow

# Sequential: Output of one feeds into next
workflow = SequentialWorkflow(agents=[researcher, analyst, writer])

# Concurrent: All run in parallel
workflow = ConcurrentWorkflow(agents=[market_analyst, risk_analyst])
```

**URL:** https://github.com/kyegomez/swarms

**Relevance to Us:**
- More production-ready than OpenAI Swarm
- Good patterns for concurrent agent execution
- Still uses API calls under the hood

**Verdict:** Good architecture patterns to adopt, but we can implement similar with Claude Code subagents.

---

### 6. CrewAI

**What it is:** Role-based multi-agent framework where agents function as teams.

**Key Features:**
- Role-based design (Researcher, Developer, etc.)
- Sequential, hierarchical, and consensus-based processes
- Built-in memory (short-term in ChromaDB, long-term in SQLite)
- Lower learning curve than LangChain

**URL:** https://www.crewai.com

**Relevance to Us:**
- Our existing agents already have roles
- Memory system is interesting
- Another framework to learn
- API costs

**Verdict:** Good ideas, but we already have role-based agents.

---

### 7. LangChain / LangGraph

**What it is:** Most comprehensive agent orchestration ecosystem with 100+ integrations.

**Key Features:**
- LangGraph for stateful workflows as graphs
- Extensive tool integrations
- Most flexible option

**URL:** https://langchain.com

**Relevance to Us:**
- Overkill for our needs
- Tends to overengineer simple tasks
- Another framework dependency

**Verdict:** Too complex for our use case.

---

### 8. Microsoft AutoGen

**What it is:** Enterprise-focused multi-agent framework with human-in-the-loop capabilities.

**Key Features:**
- Conversable agents that communicate naturally
- Sandboxed code execution (Docker)
- Custom termination conditions
- Strong Azure integration

**URL:** https://microsoft.github.io/autogen/

**Relevance to Us:**
- Good safety features (sandboxing, termination)
- Human-in-loop is relevant
- Microsoft/Azure centric

**Verdict:** Good safety patterns to learn from.

---

## Swarm Intelligence Architecture

### Philosophy

We implement swarm intelligence principles using Claude Code's native capabilities:

1. **Stigmergy**: Agents communicate indirectly via shared files (like ants leaving pheromone trails)
2. **Division of Labor**: Specialized agents handle specific domains
3. **Emergent Behavior**: Collective intelligence from agent interactions
4. **Self-Organization**: Agents decide when to hand off to others

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│           SWARM TRADING ARCHITECTURE (All on Max 5x)                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              CLAUDE CODE ORCHESTRATOR                        │    │
│  │              (tmux + --dangerously-skip-permissions)         │    │
│  │                                                               │    │
│  │  /swarm-operator or /operator-session                        │    │
│  │                                                               │    │
│  │  Spawns subagents via Task tool:                             │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │    │
│  │  │ Trading  │ │ Research │ │ Modeling │ │  Macro   │        │    │
│  │  │  Swarm   │ │  Swarm   │ │  Swarm   │ │  Swarm   │        │    │
│  │  ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤        │    │
│  │  │• critic  │ │• research│ │• regime  │ │• macro   │        │    │
│  │  │• monitor │ │• alpha   │ │• hypoth  │ │• data-acq│        │    │
│  │  │• news    │ │• brain   │ │• text    │ │          │        │    │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              STIGMERGIC COMMUNICATION                        │    │
│  │              (Shared filesystem = pheromone trails)          │    │
│  │                                                               │    │
│  │  ~/quant_results/                                            │    │
│  │  ├── live/state.json       ← Main swarm state                │    │
│  │  ├── live/signals/         ← Agents deposit findings         │    │
│  │  ├── live/swarm_state.json ← Swarm monitor state             │    │
│  │  ├── theses/               ← Collective knowledge            │    │
│  │  └── decisions/            ← Swarm decisions                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              PYTHON BACKGROUND (Cron - Free)                 │    │
│  │                                                               │    │
│  │  • Data collection (congressional, insider, news)            │    │
│  │  • State updates (LiveDaemon every 5 min)                    │    │
│  │  • Signpost monitoring                                       │    │
│  │  • Swarm health monitoring                                   │    │
│  │  • Telegram alerts                                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  COST: $100/month flat (existing subscription)                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Agent Swarms

| Swarm | Agents | Responsibility |
|-------|--------|----------------|
| **Trading** | critic, monitor, news-analyst | Real-time decisions, risk |
| **Research** | research, alpha-discovery, brainstorm | New strategies, signals |
| **Modeling** | regime-detector, hypothesis-generator, text-research | Market understanding |
| **Macro** | macro-research, data-acquisition | External factors |

### Swarm Execution Patterns

**Pattern 1: Morning Swarm (Parallel)**
```
SPAWN IN PARALLEL:
├── regime-detector-agent → regime classification
├── news-analyst-agent → overnight news
└── monitor-agent → portfolio health

THEN SEQUENTIAL:
└── Synthesize → Decide → Execute
```

**Pattern 2: Research Swarm (Pipeline)**
```
SEQUENTIAL PIPELINE:
brainstorm-agent
  → hypothesis-generator-agent
    → research-agent
      → critic-agent
```

**Pattern 3: Crisis Swarm (All Hands)**
```
SPAWN ALL IN PARALLEL:
├── monitor-agent (assess damage)
├── news-analyst-agent (find cause)
├── regime-detector-agent (regime shift?)
└── critic-agent (validate actions)

WAIT FOR ALL → Synthesize → Act
```

### Convergence Detection

When 3+ agents agree on the same symbol and direction, it becomes a **convergence** - a high-confidence signal:

```python
from src.monitoring.swarm_monitor import get_convergences

convergences = get_convergences(min_agents=3)
for c in convergences:
    print(f"{c.symbol}: {c.direction} ({c.agent_count} agents, {c.convergence_score:.0%})")
```

### Agent Trust Weights

Different agents have different trust levels for convergence scoring:

```yaml
agent_weights:
  critic-agent: 1.5      # High trust - safety critical
  monitor-agent: 1.2     # High trust - sees real data
  research-agent: 1.0    # Normal
  brainstorm-agent: 0.8  # Lower - speculative
```

---

## Implementation Details

### Files Created

| File | Purpose |
|------|---------|
| `.claude/skills/swarm-operator/SKILL.md` | Swarm orchestration skill |
| `src/monitoring/swarm_monitor.py` | Swarm activity tracking, convergence detection |

### Key Classes

**SwarmMonitor** (`src/monitoring/swarm_monitor.py`)
- Tracks agent activity and signals
- Detects convergences (multi-agent agreement)
- Persists state to `~/quant_results/live/swarm_state.json`
- Archives completed cycles

**SwarmSignal** - A signal from an agent
```python
@dataclass
class SwarmSignal:
    agent_name: str
    timestamp: datetime
    symbol: Optional[str]
    signal_type: str
    direction: str  # bullish, bearish, neutral
    confidence: float
    description: str
    metadata: dict
```

**SignalConvergence** - Multiple agents agreeing
```python
@dataclass
class SignalConvergence:
    symbol: Optional[str]
    direction: str
    signals: list[SwarmSignal]
    convergence_score: float
    agent_count: int
```

### Usage

**Start a swarm cycle:**
```python
from src.monitoring.swarm_monitor import get_swarm_monitor, SwarmType

monitor = get_swarm_monitor()
cycle = monitor.start_cycle(SwarmType.TRADING)
```

**Log a signal:**
```python
from src.monitoring.swarm_monitor import log_agent_signal

log_agent_signal(
    agent_name="news-analyst-agent",
    signal_type="earnings_catalyst",
    direction="bullish",
    confidence=0.75,
    description="SLB earnings - Venezuela commentary critical",
    symbol="SLB"
)
```

**Find convergences:**
```python
from src.monitoring.swarm_monitor import get_convergences

convergences = get_convergences(min_agents=3)
```

**Generate report:**
```python
monitor = get_swarm_monitor()
print(monitor.generate_report())
```

### Running the Swarm

**Interactive:**
```bash
cd ~/projects/quant_suite
claude
# Then: /swarm-operator
```

**Autonomous:**
```bash
tmux new-session -d -s swarm 'cd ~/projects/quant_suite && claude --dangerously-skip-permissions'
tmux attach -t swarm
# Then: "Run /swarm-operator, monitor for 4 hours"
```

---

## Key Decisions & Tradeoffs

### Decision 1: Claude Code over Agent SDK

**Choice:** Use Claude Code with --dangerously-skip-permissions instead of Claude Agent SDK

**Reasoning:**
- Max 5x subscription includes unlimited Claude Code usage
- Agent SDK uses API billing (additional cost)
- Same capabilities (tools, subagents, sessions)
- Simpler deployment (no additional code)

**Tradeoff:** Less programmatic control vs. cost savings

---

### Decision 2: Stigmergy over Direct Communication

**Choice:** Agents communicate via shared files, not direct messaging

**Reasoning:**
- Scalable (no N×N communication paths)
- Debuggable (can inspect files)
- Persistent (survives restarts)
- Natural for our existing infrastructure

**Tradeoff:** Slight latency vs. simplicity and debugging

---

### Decision 3: Convergence-Based Decisions

**Choice:** Require 3+ agents to agree before high-confidence actions

**Reasoning:**
- Reduces false positives
- Builds in redundancy
- Mimics swarm intelligence principles
- Provides audit trail

**Tradeoff:** May miss some opportunities vs. safety

---

### Decision 4: Role-Based Swarms

**Choice:** Group agents into swarms by function (Trading, Research, Modeling, Macro)

**Reasoning:**
- Clear responsibility boundaries
- Parallel execution within swarms
- Easier to reason about
- Maps to our existing agents

**Tradeoff:** Some rigidity vs. clarity

---

## Quick Reference

### Commands

```bash
# Start swarm operator
/swarm-operator

# Check swarm status
PYTHONPATH=. python3 -c "
from src.monitoring.swarm_monitor import get_swarm_monitor
print(get_swarm_monitor().generate_report())
"

# Run autonomous session
tmux new-session -d -s swarm 'cd ~/projects/quant_suite && claude --dangerously-skip-permissions'

# Watch signal files
ls -la ~/quant_results/live/signals/

# View swarm state
cat ~/quant_results/live/swarm_state.json | jq '.'
```

### File Locations

| File | Purpose |
|------|---------|
| `~/quant_results/live/state.json` | Unified system state |
| `~/quant_results/live/signals/` | Agent signals (stigmergy) |
| `~/quant_results/live/swarm_state.json` | Swarm monitor state |
| `~/quant_results/swarm_history/` | Archived swarm cycles |
| `.claude/skills/swarm-operator/SKILL.md` | Swarm skill definition |
| `src/monitoring/swarm_monitor.py` | Swarm monitoring code |

### External Resources

| Resource | URL |
|----------|-----|
| hypercontext.sh | https://hypercontext.sh |
| skill.cc | https://skill.cc |
| OpenClaw/Moltbot | https://github.com/moltbot/moltbot |
| Claude Agent SDK | https://platform.claude.com/docs/en/agent-sdk/overview |
| OpenAI Swarm | https://github.com/openai/swarm |
| Swarms Framework | https://github.com/kyegomez/swarms |
| CrewAI | https://www.crewai.com |

---

## Appendix: First Swarm Run Results

On February 1, 2026 (Sunday), we ran the first swarm cycle with 3 agents:

**Agents:** regime-detector, monitor, news-analyst
**Signals Generated:** 8
**Convergences:** 1 (MARKET: Neutral)

**Key Findings:**
1. **LEN stop loss breached** (-10.02%) - Close Monday
2. **GOLD at +49%** - Consider trim
3. **Energy at 39.4%** - No new positions (40% limit)
4. **SLB/HAL earnings** - Critical for Venezuela thesis
5. **Regime: ROTATION** - Defensive leadership, favor sector momentum

This validated the swarm architecture works within Claude Code sessions.

---

*Document created: February 1, 2026*
*Last updated: February 1, 2026*
