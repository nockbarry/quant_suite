# Athena Swarm Architecture — Breaking the Operator Monolith

## The Problem with the Current Operator

The operator session is an 8-hour Claude session that does everything:
- Mechanical monitoring (is state fresh? any alerts?) — **90% of checks**
- News interpretation (is this headline meaningful?) — **5% of checks**
- Strategic synthesis (what's the pattern across 3 days?) — **never, runs out of context**
- Trade triggering (4+ signals converged) — **rare, critical**

Result: expensive, fragile (crashes = total blindness), shallow (no time for deep thinking), and each restart loses accumulated context.

## Design Principles

1. **Separate time scales** — Real-time monitoring (seconds) shouldn't share context window with multi-day pattern recognition
2. **Python for the mechanical, Claude for the judgment** — Don't burn tokens checking if state.json is fresh
3. **Accumulated context, not fresh starts** — Every agent reads shared state and writes back to it
4. **Event-driven, not clock-driven** — Spin up analysis when something happens, not on a fixed schedule
5. **Parallel where possible** — Research on 3 topics simultaneously, not sequentially

## The Three Layers

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: SENTINEL (Python, always running, zero Claude)    │
│  Heartbeat: every 30 seconds                                │
│  Maintains: situation_board.json                             │
│  Triggers: analyst sessions when events need interpretation  │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2: REACTIVE AGENTS (Claude, on-demand, 3-10 min)    │
│  Analyst: interpret events, assess signals                  │
│  Strategist: make trade decisions                           │
│  Executor: validate and submit orders                       │
├─────────────────────────────────────────────────────────────┤
│  LAYER 3: DEEP AGENTS (Claude, scheduled + triggered)       │
│  Researcher: test hypotheses, discover patterns             │
│  Reviewer: quality control, trend tracking, forward-looking │
│  Theorist: thesis development, scenario planning            │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 1: The Sentinel

**What it is:** A Python process (no Claude) that runs continuously during market hours. It replaces both health_monitor.py and the mechanical 90% of the operator loop.

**What it does every 30 seconds:**
```
1. Read state.json → extract: prices, alerts, P&L, VIX
2. Read signal_digest.json → check for new convergences
3. Read news_cache.json → scan for urgency alerts
4. Check signpost triggers → any thesis signposts hit?
5. Check session health → any locks stale? any sessions hung?
6. Update situation_board.json with observations
7. Evaluate trigger rules → should we spin up an Analyst?
```

**Trigger rules (Python, no AI needed):**
```python
TRIGGERS = {
    "convergence":    lambda: len(new_convergences) >= 3,
    "urgency_news":   lambda: any(n["is_urgent"] for n in new_news),
    "signpost_hit":   lambda: len(triggered_signposts) > 0,
    "position_alert": lambda: any(p.unrealized_pnl_pct < -0.10 for p in positions),
    "vix_spike":      lambda: vix_change_1h > 3.0,
    "new_completion":  lambda: new_session_completed and has_actionable_findings,
}
```

When a trigger fires → Sentinel writes an analysis request to `analysis_queue.json` and spawns an Analyst session.

**What it does NOT do:** Interpret news, evaluate thesis quality, decide trades. Those require judgment.

**Cost:** Zero Claude tokens. Runs in a tmux pane. Can't crash in a way that loses context because the situation board is on disk.

---

## The Situation Board

This is the shared memory that replaces "each session reads files independently."

**File:** `~/quant_results/scheduler/situation_board.json`

```json
{
  "date": "2026-03-06",
  "last_updated": "2026-03-06T14:32:15",

  "market_snapshot": {
    "spy": 524.30, "spy_change": -0.8,
    "vix": 22.4, "vix_change_1h": 1.2,
    "regime": "risk_off_mild",
    "sector_leaders": ["XLE +1.2%", "XLV +0.4%"],
    "sector_laggards": ["XLK -1.8%", "XLC -1.1%"]
  },

  "today_observations": [
    {"time": "06:35", "source": "morning-briefing", "type": "news",
     "text": "Iran IAEA talks collapsed overnight. Oil futures +2.3%.",
     "symbols": ["XLE", "USO", "SLB"], "thesis": "Iran War Energy"},
    {"time": "09:45", "source": "sentinel", "type": "convergence",
     "text": "CF: 4 signals aligned bullish (congressional, insider, statistical, thesis)",
     "symbols": ["CF"], "thesis": "Fertilizer Agflation"},
    {"time": "10:05", "source": "analyst", "type": "assessment",
     "text": "CF convergence is strong. Congressional buy was $2.1M, unusual size. Insider buy same week. Spring planting demand imminent.",
     "symbols": ["CF"], "action": "recommend_trade"},
    {"time": "10:10", "source": "strategist", "type": "decision",
     "text": "ADD CF 27 shares @ $118.31. Thesis-aligned, multi-signal convergence.",
     "symbols": ["CF"], "decision_id": "d_20260306_1"},
    {"time": "12:05", "source": "reviewer", "type": "pattern",
     "text": "Energy thesis positions (SLB, HAL, FRO) all up >2% today. Hormuz disruption narrative strengthening. Consider if we're underweight tankers.",
     "symbols": ["SLB", "HAL", "FRO", "STNG"]}
  ],

  "active_analyses": [
    {"id": "a_001", "trigger": "urgency_news", "status": "pending",
     "context": "Reuters: 'US deploys second carrier group to Persian Gulf'",
     "requested_at": "2026-03-06T13:15:00"}
  ],

  "decisions_today": [
    {"symbol": "CF", "action": "ADD", "confidence": 0.72, "status": "executed",
     "reasoning_summary": "4-signal convergence + spring planting catalyst"}
  ],

  "portfolio_alerts": [
    {"symbol": "AXP", "type": "stop_approaching", "current_pnl": "-12.3%",
     "stop_level": "-15%", "thesis": "Bank Rate Cap (15% conviction)"}
  ],

  "regime_context": {
    "current": "risk_off_mild",
    "vix_trend_5d": "rising",
    "interpretation": "Geopolitical premium building. Favors energy, gold, defense. Pressures growth, consumer."
  }
}
```

**Every Claude session reads this first.** Every Claude session appends to `today_observations` before exiting.

The Sentinel maintains `market_snapshot`, `portfolio_alerts`, and `regime_context` continuously. Claude agents write to `today_observations`, `active_analyses`, and `decisions_today`.

---

## The Strategic Context (Multi-Day Memory)

Separate from the daily situation board. Maintained by the Reviewer agent.

**File:** `~/quant_results/scheduler/strategic_context.json`

```json
{
  "last_updated": "2026-03-06T15:00:00",
  "updated_by": "reviewer",

  "developing_patterns": [
    {
      "id": "dp_001",
      "name": "Energy insider buying acceleration",
      "first_observed": "2026-03-02",
      "days_active": 4,
      "evidence": [
        "3/2: SLB insider buy $500K",
        "3/4: HAL insider buy $320K",
        "3/5: CVX insider buy $1.2M",
        "3/6: CF congressional cluster + insider buy same week"
      ],
      "interpretation": "Smart money positioning for energy upside. Consistent with Hormuz thesis.",
      "action_suggestion": "Review energy thesis vehicle coverage. Are we in all the right names?",
      "affected_theses": ["Iran War Energy", "Fertilizer Agflation", "Venezuela Energy"]
    }
  ],

  "thesis_momentum": {
    "Iran War Energy": {"conviction_7d": [90, 92, 95, 95, 95], "trend": "stable_high"},
    "Homebuilder Mortgage": {"conviction_7d": [55, 50, 45, 40, 35], "trend": "declining",
                              "note": "Auto-invalidated 3/6 by internal-review"},
    "Fertilizer Agflation": {"conviction_7d": [75, 78, 82, 85, 85], "trend": "rising"}
  },

  "signal_source_trends": {
    "congressional": {"hit_rate_30d": 0.68, "hit_rate_7d": 0.75, "trend": "improving"},
    "wsb": {"hit_rate_30d": 0.42, "hit_rate_7d": 0.33, "trend": "declining",
            "note": "Meme cycle noise increasing"}
  },

  "upcoming_catalysts": [
    {"date": "2026-03-10", "event": "CPI Release", "affected": ["TLT", "GLD", "SPY"],
     "scenario_bull": "CPI < 3.0% → rate cut hopes → growth rally",
     "scenario_bear": "CPI > 3.5% → stagflation fear → energy/gold up, tech down"},
    {"date": "2026-03-18", "event": "MU Earnings", "affected": ["MU", "SOXX"],
     "scenario_bull": "HBM guidance raise → semiconductor rally",
     "scenario_bear": "Inventory build → correction to $85-90 range"}
  ],

  "research_hypotheses": [
    {"id": "h_001", "hypothesis": "Refiner margins expanding faster than oilfield services revenue when oil spikes above $80",
     "status": "untested", "suggested_by": "brainstorm 3/3",
     "test_plan": "Backtest PBF vs SLB relative performance in oil spike regimes"},
    {"id": "h_002", "hypothesis": "Congressional buying predicts sector rotation 2-4 weeks ahead",
     "status": "partially_tested", "suggested_by": "researcher 3/1",
     "finding": "IC=0.15 on 6-month sample. Need more data."}
  ],

  "open_questions": [
    "Are we overexposed to Hormuz disruption? What if negotiations succeed?",
    "Should we add European defense names (EUAD, Rheinmetall) to defense thesis?",
    "Fertilizer thesis: is CF the best vehicle or should we diversify to MOS/NTR?"
  ]
}
```

**Who reads it:** Morning briefing, strategist (trade-decision), reviewer, theorist.
**Who writes it:** Reviewer (primary maintainer, 2x daily), theorist (weekly), researcher (when findings relevant).

---

## Layer 2: Reactive Agents

### Analyst (Claude, on-demand, 3-5 min, sonnet)

**Triggered by:** Sentinel when events need interpretation.

**What it does:**
- Reads the analysis request from `analysis_queue.json`
- Reads situation board for context
- Reads strategic context for multi-day patterns
- Produces a focused assessment: "Is this actionable? What does it mean for our theses?"
- Writes assessment back to situation board
- If actionable → flags for strategist

**Examples of analyst triggers:**
- "3 signals converged on STNG — is this a new position or noise?"
- "Reuters headline about Iran talks — does this change our energy thesis?"
- "VIX spiked 3 points in 30 min — regime shift or noise?"
- "Morning briefing found 5 thesis-matched headlines — which matter most?"

**Key property:** Short, focused, cheap. One question in, one assessment out.

### Strategist (Claude, on-demand + scheduled, 10 min, opus)

**Triggered by:** Analyst recommends trade, scheduled at 10:00/13:00, or Sentinel detects critical trigger.

**What it does:**
- This IS the current /trade-decision but with richer context
- Reads full situation board (not just state.json)
- Reads strategic context (multi-day patterns, upcoming catalysts)
- Has all of today's observations from Sentinel + Analyst
- Makes decisions with full accumulated context

**Key difference from current:** The strategist doesn't need to "discover" what happened today — the situation board already has the day's narrative. It can focus entirely on judgment.

### Executor (Python + Claude validation, 2 min)

**Triggered by:** Strategist creates decision.

**What it does:**
- This is cron_auto_execute.py but smarter
- Python validates: risk limits, PDT, position sizing, sector exposure
- If validation passes AND confidence > threshold → execute automatically (paper)
- If edge case → spawn a 2-min Claude session for judgment ("this would put energy at 35% — proceed?")

---

## Layer 3: Deep Agents

### Researcher (Claude, event-triggered + scheduled, 15-20 min, sonnet)

**Triggered by:** Strategic context has untested hypotheses, analyst flags something needing investigation, weekly schedule.

**What it does:**
- Tests hypotheses from `research_hypotheses` in strategic context
- Runs backtests, MCPT validation
- Can run in parallel (3 researchers on different topics)
- Writes findings to strategic context + research database

**Key improvement:** Currently research runs on a fixed schedule and may investigate things that don't matter. Event-triggered research investigates what the system actually needs answers to.

**Example:** Analyst assesses a convergence on STNG, notes "we don't have a tanker thesis — should we?" → Researcher is triggered to investigate tanker fundamentals, backtest the signal, and propose a thesis.

### Reviewer (Claude, 2x daily, 10 min, sonnet)

**Triggered by:** Schedule (noon, 3 PM) + end of day.

**What it does:**
- This IS /internal-review but expanded
- Maintains `strategic_context.json` (the multi-day memory)
- Identifies developing patterns across days
- Updates thesis momentum trends
- Checks signal source quality trends
- Generates upcoming catalyst scenarios
- Flags open questions for researcher/theorist
- Auto-invalidates low-conviction theses (already implemented)

**Key property:** This is the agent that "looks up" from the day-to-day and asks "what's the bigger picture?"

### Theorist (Claude, weekly + triggered, 15 min, opus)

**Triggered by:** Weekly schedule (Sunday), reviewer flags a strategic question.

**What it does:**
- Reviews all theses holistically
- Generates new thesis candidates from developing patterns
- Scenario-plans for upcoming catalysts
- Identifies portfolio blind spots
- Proposes research hypotheses
- Updates strategic context with forward-looking analysis

**Example output:** "Energy positions are heavily weighted toward production (SLB, HAL) but Hormuz disruption primarily benefits transportation (tankers, pipelines) and downstream (refiners). Portfolio is positioned for the wrong part of the value chain."

---

## How Information Flows Between Agents

```
                         strategic_context.json
                        (multi-day, maintained by Reviewer)
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌──────────┐      ┌──────────────┐      ┌───────────┐
    │ Theorist │      │  Researcher  │      │  Reviewer  │
    │ (weekly) │      │ (on-demand)  │      │ (2x daily) │
    └────┬─────┘      └──────┬───────┘      └─────┬─────┘
         │                   │                    │
         └───────────┬───────┘                    │
                     ▼                            │
              research findings                   │
              thesis proposals                    │
                     │                            │
                     ▼                            ▼
              situation_board.json ◄───────── pattern updates
             (daily, maintained by Sentinel)  quality checks
                     │
          ┌──────────┼──────────┐
          │          │          │
          ▼          ▼          ▼
    ┌─────────┐ ┌──────────┐ ┌──────────┐
    │ Analyst │ │Strategist│ │ Executor │
    │(on-demand)│(scheduled)│ │(auto)    │
    └────┬────┘ └────┬─────┘ └────┬─────┘
         │          │             │
         ▼          ▼             ▼
    assessments  decisions     orders
         │          │             │
         └──────────┴─────────────┘
                    │
                    ▼
            situation_board.json
            (observations appended)
                    │
                    ▼
              Sentinel reads
              (every 30 sec)
```

**The circle is complete:** Sentinel observes → triggers Analyst → Analyst assesses → triggers Strategist → Strategist decides → Executor acts → Sentinel observes result → Reviewer synthesizes → strategic context informs tomorrow's Analyst/Strategist.

---

## Regime-Adaptive Behavior

The Sentinel adjusts behavior based on market regime:

| Regime | Sentinel Interval | Analyst Trigger Threshold | Trade Sessions | Research |
|--------|-------------------|--------------------------|----------------|----------|
| **Low vol** (VIX < 15) | 60 sec | 4+ convergences | 2x daily | Background |
| **Normal** (VIX 15-25) | 30 sec | 3+ convergences | 2x daily | Normal |
| **Elevated** (VIX 25-35) | 15 sec | 2+ convergences | 3x daily | Focused on risk |
| **Crisis** (VIX > 35) | 10 sec | Any convergence | On every trigger | Paused (focus on positions) |

In crisis mode, Sentinel becomes hyper-vigilant and triggers Analyst on every significant move. The Strategist gets called more frequently. Research pauses to free up resources for position management.

---

## Migration Path (Incremental)

### Phase 1: Situation Board (can do now)
- Create `situation_board.json` format
- Modify session_wrapper.sh to inject "read situation board first, append observations before exit"
- Modify existing skills to read/write situation board
- No new agents needed — existing skills just share memory better

### Phase 2: Sentinel (replace health_monitor)
- Expand health_monitor.py into sentinel.py
- Add: convergence detection, news scanning, signpost checks (currently in operator)
- Add: situation board maintenance
- Add: analysis queue + trigger rules
- Keep operator session but it now just reads situation board instead of checking everything itself

### Phase 3: Break Apart the Operator
- Operator becomes the Analyst (short, triggered sessions)
- Add Strategist as enhanced trade-decision
- Sentinel handles all monitoring
- Operator session goes away entirely

### Phase 4: Deep Agents
- Reviewer maintains strategic context
- Researcher becomes event-triggered
- Theorist added for weekly strategic thinking
- Full swarm operational

---

## What This Costs vs Current

| Metric | Current (Operator Monolith) | Swarm Architecture |
|--------|----------------------------|-------------------|
| Claude tokens/day | ~500K (8h opus session) | ~200K (many short sessions) |
| Response to events | 1-3 min (operator check interval) | 30 sec (Sentinel) + 3 min (Analyst) |
| Context depth | Shallow (one context window) | Deep (situation board + strategic context) |
| Research parallelism | Sequential (one session at a time) | Parallel (3+ researchers) |
| Failure blast radius | Total (operator crash = blind) | Isolated (Sentinel always running) |
| Multi-day pattern recognition | None (context resets daily) | Explicit (strategic_context.json) |
| Cost of mechanical checks | ~400K tokens (90% of operator) | Zero (Python Sentinel) |
| Forward-looking analysis | Incidental | Systematic (Theorist + catalysts) |

---

## Key Insight

The current system's information problem isn't collection (35+ sources is plenty) or processing (signal digest is clean). It's **synthesis across time scales**.

The situation board gives same-day synthesis. The strategic context gives multi-day synthesis. The Theorist gives forward-looking synthesis. Each layer accumulates what the layer below discovers, so agents at every time scale have access to the full picture without needing to rebuild it from scratch.

The Sentinel is the backbone — cheap, always running, never loses context. Claude agents are the brain — expensive, called only when judgment is needed, given rich accumulated context so they can focus on what they're good at: reasoning under uncertainty.
