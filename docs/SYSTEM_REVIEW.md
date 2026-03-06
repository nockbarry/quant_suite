# Athena System Review — Information Flows & Improvement Opportunities

*Generated 2026-03-06 from full codebase audit*

---

## What the System Does Today

```
DATA (35+ sources, every 30 min)
  │
  ├─ collect_all_data.py ──→ news_cache.json, alt_data, screens, social
  ├─ cron_signal_scan.py ──→ latest_scan.json (WSB, Stocktwits, prediction markets)
  ├─ LiveDaemon (5 min) ───→ state.json (THE ONE FILE)
  │
  ▼
SIGNAL PROCESSING (every 30 min)
  │
  ├─ cron_signal_digest.py ──→ signal_digest.json
  │   Quality-weighted, recency-decayed, deduplicated
  │   Source weights: congressional 1.4x → stocktwits 0.7x
  │
  ▼
CLAUDE SESSIONS (6 autonomous sessions/day)
  │
  ├─ 06:30  /morning-briefing ──→ briefings/, SessionContext
  ├─ 08:30  /operator-session ──→ operator_log.jsonl, trade_triggers.json
  ├─ 10:00  /trade-decision   ──→ decisions, predictions, auto-execute
  ├─ 13:00  /trade-decision   ──→ decisions, predictions, auto-execute
  ├─ 16:30  /eod-review       ──→ learnings, belief updates, calibration
  │
  ▼
FEEDBACK LOOP (daily)
  │
  ├─ 17:15  cron_prediction_scorer ──→ scored predictions
  ├─ 17:30  cron_belief_update     ──→ calibration, signal weight adjustments
  └─────→ Next morning briefing reads calibration ──→ cycle repeats
```

**19 cron jobs** (10 data, 9 autonomous Claude). **16 skills**. **51 positions** across 23 active theses.

---

## What Works Well

| Flow | Why It Works |
|------|-------------|
| **Morning → Decision → Execute** | Tight pipeline. Briefing at 6:30, decision at 10:00, auto-execute within seconds. <30 min from signal to order. |
| **Operator → Trade Triggers** | Persistent loop detects 4+ signal convergence, writes trigger, health monitor launches trade-decision. Real-time reactive. |
| **Learning Loop** | EOD extracts learnings → belief updater adjusts weights → morning briefing reads calibration → decisions get confidence-adjusted. True 24-hour feedback. |
| **Signal Deduplication** | 35+ raw sources → quality-weighted digest → one file. Operator reads 1 file instead of 5+. Congressional trades weighted 1.4x, Stocktwits 0.7x. |
| **News → Thesis Matching** | 1801 keywords, 16 RSS feeds. Headlines auto-matched to theses. Operator sees thesis-relevant news immediately. |
| **Self-Healing** | Internal review auto-invalidates sub-40% theses, health monitor restarts dead operator, smart_completion extracts findings when Claude forgets. |

---

## Gaps & Improvement Opportunities

### Tier 1: Easy Fixes (< 1 hour each)

**1. Congressional/Insider data collected once at 7 AM**
- Form 4 filings happen throughout the day. Current setup misses afternoon insider buys.
- *Fix*: Move congressional + insider into collect_all_data.py's extended set (already there, just verify it runs every 30 min not just once).
- *Status*: Already in collect_all_data.py but only runs in non-`--quick` mode. The cron runs `--quick`. Change cron to run full collection every 2h, quick every 30 min.

**2. Some alternative signals in state.json have no producer**
- `weather_signals`, `fda_calendar`, `squeeze_candidates` referenced in briefing skill but unclear if actively populated.
- *Fix*: Audit state.json for empty/stale fields. Either populate or remove references.

**3. Belief updater runs once daily at 5:30 PM**
- Intraday signal quality degradation goes undetected until next morning.
- *Fix*: Run a lightweight mid-day belief check (noon) that flags large deviations without full recomputation.

### Tier 2: Medium Improvements (2-4 hours each)

**4. Prediction scoring is delayed 4-6 hours**
- Predictions created at 10:00 AM, scored at 5:15 PM. Fast-closing positions may resolve before scoring.
- *Fix*: Add a lightweight position-close hook in the state update cycle. When a position closes, immediately score its linked prediction.

**5. Research insights don't reliably surface to operator**
- 112 insights in session_tracker but operator only reads completion records, not insight DB.
- *Fix*: Have `/research` write a `research_highlights.json` that operator ingests (like it already does for social signals).

**6. No intraday signal quality feedback**
- Signal quality tracker only updates at EOD. A signal source could be producing garbage all day.
- *Fix*: Track signal-to-outcome at each state refresh. If a source's last 5 signals all went wrong, temporarily down-weight in the digest.

**7. SessionContext pollution between sessions**
- SessionContext is a singleton. If not reset between sessions, context from morning-briefing could leak into trade-decision.
- *Fix*: session_wrapper.sh already sets autonomous_mode.json per-session. Add explicit `SessionContext.reset()` at session start.

### Tier 3: Architectural Improvements (day+ each)

**8. Operator session is a monolith**
- The operator does: state monitoring, news ingestion, convergence detection, session coordination, thesis monitoring, trade trigger generation — all in one 8-hour Claude session.
- *Problem*: If it crashes at hour 3, everything stops until health_monitor restarts it. Context from hours 1-3 is lost.
- *Fix*: Split into lightweight Python monitoring loop (always running, no Claude needed) + on-demand Claude sessions when human-level judgment required. The Python loop handles: state checks, convergence detection, signpost triggers, data freshness. Claude sessions triggered only for: complex convergences, ambiguous news, thesis evaluation.
- *Benefit*: 90% of operator checks are mechanical (is state fresh? any alerts? any convergences?). Only 10% need Claude reasoning.

**9. No cross-session memory within a day**
- Morning briefing context doesn't flow into trade-decision except through files.
- Trade-decision context doesn't flow into afternoon trade-decision.
- *Current*: Each Claude session starts fresh, reads files, rebuilds context.
- *Fix*: A `session_context_today.json` file that accumulates key observations across sessions. Each session reads it at start and appends to it at end.
- *Benefit*: Afternoon trade-decision knows what morning briefing found and what the first trade-decision decided.

**10. No regime-adaptive scheduling**
- Same schedule runs whether VIX is 12 or 40. High-vol days need more frequent checks.
- *Fix*: Health monitor reads VIX from state.json. If VIX > 25, switch signal digest to every 15 min and add a 2:30 PM trade-decision session. If VIX > 35, add hourly trade decisions.

**11. No backtesting of signal quality weights**
- Source weights (congressional 1.4x, WSB 0.8x) are hand-tuned.
- *Fix*: Weekly `/internal-review` Sunday pass should compute actual hit rates per source over trailing 30 days and update `SOURCE_WEIGHTS` in cron_signal_digest.py if they've drifted >10% from current values.

---

## Information Flow Diagram

```
                    ┌──────────────────────────────────────────┐
                    │           RAW DATA SOURCES                │
                    │  RSS(16) WSB Finviz(8) Congressional     │
                    │  Insider Options Prediction_Markets       │
                    │  Stocktwits Geopolitical Legal Sectors    │
                    └──────────────┬───────────────────────────┘
                                   │ every 30 min
                                   ▼
                    ┌──────────────────────────────────────────┐
                    │       collect_all_data.py                 │
                    │   + cron_signal_scan.py (2h)             │
                    │   + LiveDaemon (5 min)                    │
                    └──────┬──────────┬───────────┬────────────┘
                           │          │           │
              news_cache   │   latest_scan  alt_data/signals
                    .json  │      .json        .json
                           │          │           │
                           ▼          ▼           ▼
                    ┌──────────────────────────────────────────┐
                    │       cron_signal_digest.py               │
                    │  Quality weight → Recency decay →        │
                    │  Deduplicate → Detect convergences        │
                    └──────────────┬───────────────────────────┘
                                   │
                          signal_digest.json
                                   │
                                   ▼
             ┌─────────────────────────────────────────────────┐
             │              state.json (THE ONE FILE)           │
             │  market_regime | portfolio | positions | signals │
             │  theses | alerts | news_events | learnings       │
             └────┬────────┬────────┬────────┬────────┬────────┘
                  │        │        │        │        │
     ┌────────┐  │  ┌─────┴──┐  ┌──┴───┐  ┌┴─────┐  │  ┌────────┐
     │morning-│  │  │operator│  │trade-│  │eod-  │  │  │internal│
     │briefing│  │  │session │  │decis.│  │review│  │  │-review │
     │ 6:30am │  │  │8:30-4pm│  │10/1pm│  │4:30pm│  │  │12/3pm  │
     └───┬────┘  │  └───┬────┘  └──┬───┘  └──┬───┘  │  └───┬────┘
         │       │      │          │          │      │      │
    briefing  signal  operator   decision   learn  signal  auto-
     .json    -scan    _log     + predict   -ings  -scan  invalidate
              10:30   .jsonl    + execute    .json  14:30   theses
              14:30     │         │            │              │
                        │         │            │              │
                        ▼         ▼            ▼              ▼
              trade_triggers  auto_execute  belief_update   ProcessEvent
                  .json      (paper)       5:30pm          (audit)
                    │                         │
                    │                         │
                    └────────→ NEXT DAY ◄─────┘
                          morning-briefing
                          reads calibration
```

---

## Summary Scorecard

| Dimension | Grade | Notes |
|-----------|-------|-------|
| **Data Collection** | A- | 35+ sources, parallel collection, good coverage. Missing: intraday insider refresh. |
| **Signal Processing** | A | Quality-weighted, deduplicated, convergence detection. Clean pipeline. |
| **Decision Pipeline** | A | Context builder + adversarial + pre-mortem + auto-predictions. Solid. |
| **Execution** | B+ | Auto-execute works for paper. No live execution path yet. |
| **Learning Loop** | A- | Daily belief update + calibration + learnings. Missing: intraday feedback. |
| **Self-Healing** | B+ | Internal review auto-invalidates, health monitor restarts. Missing: regime-adaptive scheduling. |
| **Cross-Session Context** | C+ | Each session reads files independently. No accumulated daily context. |
| **Operator Efficiency** | B- | Monolithic 8-hour Claude session. 90% of checks could be Python-only. |
| **Scheduling** | B | Fixed schedule regardless of market regime. |
| **Observability** | B+ | ProcessEvents, operator_log, completions. Could surface more in web UI. |

**Overall: B+** — The core pipeline (data → signals → decisions → execution → learning) is tight and well-connected. Main opportunities are in making the operator lighter, adding cross-session memory, and making the schedule regime-adaptive.
