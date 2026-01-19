# System Cohesion Audit

**Date**: 2026-01-19
**Purpose**: Ensure all components work together effectively as a unified trading system

---

## Executive Summary

The system has **strong foundational architecture** but suffers from **information fragmentation**. The core trading workflow is coherent, but supporting documentation and research artifacts are scattered, making it harder for me (Claude) to maintain full context across sessions.

### Overall Assessment: 7/10

**Strengths**: Unified state, skill/agent architecture, cron automation, thesis tracking
**Weaknesses**: Orphan files, scattered documentation, unused data sources, session context gaps

---

## 1. Context Loading Analysis

### What Loads Automatically (Good)

| Component | Source | Loaded When |
|-----------|--------|-------------|
| CLAUDE.md | Project root | Every session start |
| Trading Rules | CLAUDE.md | Every session |
| Skill definitions | .claude/skills/*/SKILL.md | When skill invoked |
| Agent definitions | .claude/agents/*.md | When agent spawned |

### What Must Be Manually Loaded

| Component | Source | Should Be Loaded When |
|-----------|--------|----------------------|
| Unified State | `~/quant_results/live/state.json` | Every trading session |
| Trading Patterns | `docs/TRADING_PATTERNS.md` | Thesis creation, morning briefing |
| Recent Learnings | `~/quant_results/learnings/2026-01.json` | Trade decisions |
| Active Theses | `~/quant_results/theses/*.yaml` | Via unified state |

### Gap: Session Context Not Preserved

The file `~/quant_results/sessions/claude_session_context.json` was last updated **2026-01-02** and contains:
```json
{
  "focus_strategy": "options_enhanced_momentum",
  "session_id": "20260102_225430"
}
```

This is 17 days stale and not being used. Either:
1. Remove this vestigial system, OR
2. Integrate it into skill endings to preserve context

---

## 2. File Organization Issues

### Orphan Files at Root (Should Be Archived/Removed)

| File | Size | Last Modified | Status |
|------|------|---------------|--------|
| `NEXT_STEPS.md` | 9KB | Jan 3 | **STALE** - From initial setup |
| `PROGRESS.md` | 46KB | Jan 2 | **STALE** - Initial implementation log |
| `TODO_IMPLEMENTATION_PLAN.md` | 30KB | Jan 11 | **STALE** - Plan mode artifact |
| `SYSTEM_DIAGNOSTIC.md` | 19KB | Jan 11 | **STALE** - One-time diagnostic |
| `trading_suite_requirements.md` | 53KB | Jan 3 | **REFERENCE** - Original requirements |
| `trading_suite_budget_edition.md` | 20KB | Jan 3 | **REFERENCE** - Budget constraints |
| `venezuela_plan.md` | 36KB | Jan 5 | **REFERENCE** - Specific thesis research |
| `brainstorm_*.py` (3 files) | ~90KB | Jan 5 | **MISPLACED** - Should be in scripts/ |
| `scan_*.py` (2 files) | ~25KB | Jan 5 | **MISPLACED** - Should be in scripts/ |

### Recommendation
```bash
# Archive stale planning docs
mkdir -p archive/planning
mv NEXT_STEPS.md PROGRESS.md TODO_IMPLEMENTATION_PLAN.md SYSTEM_DIAGNOSTIC.md archive/planning/

# Move scripts to proper location
mv brainstorm_*.py scan_*.py simple_scan.py scripts/research/
```

---

## 3. Documentation Coherence

### Current Documentation Map

```
CLAUDE.md (21KB)                    <- PRIMARY: Always loaded
├── Trading Rules
├── Skill Reference
├── Agent Reference
└── Quick Commands

docs/
├── WORKFLOW.md (7KB)               <- How daily trading works
├── TRADING_PATTERNS.md (9KB)       <- Meta-learnings (NEW)
├── ALTERNATIVE_DATA_OPPORTUNITIES.md (15KB) <- Future work (NEW)
├── TRADING_GUIDE.md (14KB)         <- End-user guide
├── EVALUATION_API.md (12KB)        <- Backtesting reference
├── ALPHA_DISCOVERY.md (9KB)        <- Alpha finding methods
├── TEXT_RESEARCH.md (7KB)          <- Text/NLP research
├── FREE_DATA_SOURCES.md (15KB)     <- Data source docs
├── ARCHITECTURE_DIAGRAMS.md (107KB) <- System architecture
├── REALTIME_DATA_SPEC.md (38KB)    <- Real-time infrastructure
└── DATA_SOURCE_RECOMMENDATIONS.md (9KB) <- Data priorities
```

### Issues Found

1. **Overlap**: `TRADING_GUIDE.md` and `WORKFLOW.md` cover similar territory
2. **Missing**: No single "system overview" document for new sessions
3. **Stale root files**: Competing with docs/ folder

### Recommendation: Create System Map

Add to CLAUDE.md a clear documentation hierarchy:
```markdown
## Documentation Guide
- **Daily Trading**: docs/WORKFLOW.md
- **Meta-Learnings**: docs/TRADING_PATTERNS.md
- **Architecture**: docs/ARCHITECTURE_DIAGRAMS.md
- **Data Sources**: docs/FREE_DATA_SOURCES.md
```

---

## 4. Workflow Coherence Assessment

### Daily Trading Flow: COHERENT

```
6:00 AM  ─► research_prep.py (cron)
         │
6:05 AM  ─► LiveDaemon updates state.json (cron, every 5 min)
         │
6:30 AM  ─► User: /morning-briefing
         │   └── Reads state.json + searches news
         │
9:30 AM  ─► Market opens
         │
Anytime  ─► User: /trade-decision
         │   └── Consumes state, applies adversarial analysis
         │
Anytime  ─► User: /execute-trades
         │   └── Executes with human approval
         │
4:00 PM  ─► Market closes
         │
4:30 PM  ─► User: /eod-review
         │   └── Extracts learnings, updates theses
         │
5:00 PM  ─► eod_snapshot.py (cron)
```

**Status**: This workflow is well-designed and functional.

### Research Flow: PARTIALLY COHERENT

```
/research or research-agent
    │
    ├── Uses: FeatureEngine, BacktestEngine, MCPTAnalyzer
    │
    ├── Outputs to: ~/quant_results/research_sessions/
    │              ~/quant_results/research_tracker/
    │              ~/quant_results/experiments/
    │
    └── Should feed into: Thesis creation, strategy promotion
```

**Issue**: Research outputs don't automatically surface in morning briefings or trade decisions. The `research_tracker/insights.json` has 162KB of insights that aren't being consumed.

### Thesis Flow: COHERENT

```
/thesis create → ~/quant_results/theses/{id}.yaml
       │
       ├── Linked to positions
       ├── Signpost tracking (cron_thesis_signpost_check.py)
       ├── Conviction history
       │
       └── Performance tracking (ThesisPerformanceTracker)
```

**Status**: Well-integrated with unified state and learnings.

---

## 5. Data Flow Analysis

### What's Connected

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONNECTED DATA FLOWS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Alpaca API ──► LiveDaemon ──► state.json ──► Skills            │
│       │                            │                            │
│       │                            ├──► Theses                  │
│       │                            ├──► Positions               │
│       │                            ├──► Risk metrics            │
│       │                            └──► Learnings (recent)      │
│       │                                                         │
│  Cron Jobs ──► Congressional data ──► state.json (alt_data)     │
│            ──► Insider data                                     │
│            ──► News collection                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### What's Disconnected

```
┌─────────────────────────────────────────────────────────────────┐
│                  DISCONNECTED DATA FLOWS                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  research_tracker/insights.json (162KB)                         │
│      └── Contains strategy insights                             │
│      └── NOT consumed by morning briefing or trade decisions    │
│                                                                 │
│  sessions/claude_session_context.json                           │
│      └── Last updated: 2026-01-02 (17 days stale)               │
│      └── NOT being written or read                              │
│                                                                 │
│  32+ Alternative Data Sources (implemented but unused)          │
│      └── Weather, FDA calendar, job postings, app rankings      │
│      └── NOT generating signals or alerts                       │
│                                                                 │
│  Chat History (54MB in .claude/projects/)                       │
│      └── Available for reference                                │
│      └── NOT indexed or searchable                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Knowledge Persistence Assessment

### Working Well

| System | Location | Status |
|--------|----------|--------|
| Theses | `~/quant_results/theses/*.yaml` | 18 active, conviction tracking works |
| Learnings | `~/quant_results/learnings/2026-01.json` | 8+ learnings this month |
| Decisions | `~/quant_results/decisions/` | Daily files being created |
| EOD Reviews | `~/quant_results/eod_reviews/` | 4 reviews this month |
| Unified State | `~/quant_results/live/state.json` | Updated every 5 min |

### Not Working

| System | Issue |
|--------|-------|
| Session Context | Stale since Jan 2 |
| Research Insights | 162KB not consumed |
| Knowledge Base | `~/quant_results/knowledge/` sparse |
| Company Briefs | Few entries |

---

## 7. Recommendations

### Priority 1: Immediate Cleanup

```bash
# 1. Archive stale root files
mkdir -p archive/planning_2026_01
mv NEXT_STEPS.md PROGRESS.md TODO_IMPLEMENTATION_PLAN.md SYSTEM_DIAGNOSTIC.md archive/planning_2026_01/

# 2. Move misplaced scripts
mkdir -p scripts/research
mv brainstorm_*.py scan_january_anomalies.py simple_scan.py scripts/research/

# 3. Remove or update stale session context
rm ~/quant_results/sessions/claude_session_context.json
```

### Priority 2: Connect Disconnected Data

1. **Add research insights to morning briefing**:
   - Modify `/morning-briefing` to check `research_tracker/insights.json`
   - Surface unimplemented but validated insights

2. **Activate unused data sources**:
   - Create cron jobs for weather, FDA calendar, job postings
   - Add to unified state's `alt_data` section

3. **Surface learnings in trade decisions**:
   - Load recent learnings by tag when making decisions
   - "Last time we traded energy with 50% concentration, we lost..."

### Priority 3: Documentation Consolidation

1. **Add to CLAUDE.md**: Documentation guide section
2. **Archive**: Old requirement docs to archive/
3. **Create**: Single "System Overview" section at top of CLAUDE.md

### Priority 4: Consider Chat History Integration

The `.claude/projects/` folder has 54MB of conversation history. Options:
1. **Ignore**: Current approach, works fine
2. **Index key insights**: Extract major decisions/learnings into searchable format
3. **Session summaries**: Auto-generate summaries at session end

---

## 8. Information Flow Diagram (Ideal State)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        IDEAL INFORMATION FLOW                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                  │
│  │ CLAUDE.md   │    │ Unified     │    │ Trading     │                  │
│  │ (rules)     │ +  │ State       │ +  │ Patterns    │ = Full Context   │
│  └─────────────┘    │ (state.json)│    │ (meta)      │                  │
│                     └─────────────┘    └─────────────┘                  │
│         │                  │                  │                         │
│         ▼                  ▼                  ▼                         │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                   MORNING BRIEFING                       │           │
│  │  - Market state (from unified)                          │           │
│  │  - Portfolio (from unified)                             │           │
│  │  - Theses (from unified)                                │           │
│  │  - Recent learnings (from unified)                      │           │
│  │  - Research insights (NEW: from research_tracker)       │           │
│  │  - Alt data signals (NEW: weather, FDA, etc.)           │           │
│  └─────────────────────────────────────────────────────────┘           │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                   TRADE DECISION                         │           │
│  │  - Applies patterns (vehicle enum, converging signals)  │           │
│  │  - Adversarial analysis                                 │           │
│  │  - Thesis linking                                       │           │
│  │  - Relevant learnings surfaced                          │           │
│  └─────────────────────────────────────────────────────────┘           │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────┐           │
│  │                   EOD REVIEW                             │           │
│  │  - Extract learnings → learnings.json                   │           │
│  │  - Update thesis conviction                             │           │
│  │  - Surface patterns for TRADING_PATTERNS.md             │           │
│  │  - (NEW: Update session context)                        │           │
│  └─────────────────────────────────────────────────────────┘           │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Action Items Summary

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| P1 | Archive stale root files | 5 min | Medium (cleaner context) |
| P1 | Move misplaced scripts | 5 min | Low (organization) |
| P2 | Add research insights to briefing | 1 hr | High (surface forgotten insights) |
| P2 | Activate 3-5 unused data sources | 2 hrs | High (more signals) |
| P2 | Add doc guide to CLAUDE.md | 10 min | Medium (clearer navigation) |
| P3 | Consider session summary system | 2 hrs | Medium (context preservation) |

---

## 10. Conclusion

The system is **architecturally sound** but has **accumulated cruft** from rapid development. The core trading workflow (briefing → decision → execute → review) works well. The main issues are:

1. **Disconnected research artifacts** - insights generated but not consumed
2. **Orphan documentation** - competing files at root vs docs/
3. **Unused data sources** - 32+ implemented, <10 actively generating signals

The newly created `TRADING_PATTERNS.md` addresses meta-learning persistence. The next step is to connect the remaining disconnected pieces, particularly surfacing research insights and activating more data sources.

**Bottom line**: A few hours of cleanup and connection work would significantly improve system cohesion.
