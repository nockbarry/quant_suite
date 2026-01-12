# Quant Suite Development Log

**Purpose**: Track development progress, decisions, and issues
**Created**: 2026-01-04

---

## 2026-01-11: Data Pipeline Fixes & Automation

### Summary
- Fixed critical data flow issues in research prep pipeline
- Added insider data collection automation
- Implemented concentration alert monitoring
- Expanded cron automation to 7 jobs

### Fixes Applied

| Issue | Fix | Impact |
|-------|-----|--------|
| Feature Engine method mismatch | Changed `compute_all_features` to `add_all_features` in research_prep.py | Features now compute correctly |
| Column name mismatch | Added column normalization (yfinance returns "Close", FeatureEngine expects "close") | Features populate properly |
| Missing insider cron | Created `cron_insider_collect.py` with archive support | Daily insider data collection |
| No concentration alerts | Added `check_concentration()` to AlertManager | Position/sector/thesis limits monitored |

### Cron Jobs (7 total)

| Job | Schedule | Purpose |
|-----|----------|---------|
| research_prep | 6:00 AM weekdays | Pre-compute features and signals |
| news_collect | Every 4 hours | News aggregation |
| congressional_collect | 6:30 AM daily | Congressional trades |
| insider_collect | 7:00 AM daily | Insider trading data |
| live_daemon_check | Every 5 min weekdays | State.json updates |
| eod_snapshot | 5:00 PM weekdays | Daily archives |
| concentration_check | Every 15 min market hours | Limit monitoring |

### Future Enhancements

| Enhancement | Priority | Notes |
|-------------|----------|-------|
| ML Signal Integration | P2 | Currently returns 0 - needs model integration |
| VIX Term Structure | P1 | Per free data source plan |
| AAII Sentiment | P1 | Per free data source plan |
| COT Report | P1 | Per free data source plan |

### Files Modified/Created
- `scripts/research_prep.py` - Fixed method calls and column names
- `scripts/cron_insider_collect.py` - NEW: Daily insider collection
- `scripts/cron_concentration_check.py` - NEW: Limit monitoring
- `scripts/setup_cron.py` - Added 2 new cron jobs
- `src/data/sources/alternative/insider.py` - Added `get_recent_insider_buys()`
- `src/alerts/alert_manager.py` - Added `check_concentration()`

---

## 2026-01-04: Consolidation and Documentation

### Summary
- Scanned all quant_results for research insights
- Identified valid vs potentially false results
- Created DEVLOG.md and RESEARCH_LOG.md
- Updated documentation with consolidated findings

### Key Decisions Made

1. **Regime-Based Strategy Selection**: Implemented EmpiricalRegimeClassifier based on analysis of 470+ strategy/symbol combinations
2. **Focus on Mid/Small Caps**: Large caps (SPY, QQQ, AAPL) too efficient (3.8% win rate); mid/small caps show 14.9% win rate
3. **PDT Compliance**: All strategies optimized for <$25k accounts with min 2-day holds

### Issues Identified

| Issue | Status | Notes |
|-------|--------|-------|
| ML strategies lack MCPT validation | **FLAGGED** | XGBoost shows Sharpe 1.77 but no p-value documented |
| Mid/small cap feature leakage | **UNRESOLVED** | User mentioned past issues but not documented in results |
| Multi-signal AMD borderline | **MONITOR** | p=0.045 is at threshold |

### Files Modified
- README.md (added regime framework)
- CLAUDE.md (added regime detection)
- Created DEVLOG.md
- Created RESEARCH_LOG.md

---

## 2026-01-03: Multi-Agent Orchestration Complete

### Summary
- Deployed 10 Claude Code agents for autonomous operation
- Implemented dual-track research (Novel Patterns + Strategy Testing)
- Created PDT strategy pool framework

### Agents Deployed
1. macro-research-agent
2. news-analyst-agent
3. regime-detector-agent
4. research-agent
5. research-worker-agent
6. text-research-agent
7. critic-agent
8. monitor-agent
9. brainstorm-agent
10. orchestrator-agent

### Production-Ready Strategies Found
- bollinger_reversal/QCOM: Sharpe 3.14, p=0.007
- bollinger_reversal/MU: Sharpe 2.93, p=0.007
- bollinger_reversal/MRVL: Sharpe 2.71, p=0.017
- bollinger_reversal/IWM: Sharpe 2.34, p=0.040
- momentum/AMD: Sharpe 2.11, p=0.047

---

## 2026-01-02: Text Research Framework

### Summary
- Built text-based alpha research system
- Implemented point-in-time safe corpus storage
- Created 7 text features and 6 signal strategies

### Key Design Choices
- **signal_delay=1**: Same-day text generates next-day signals (prevents lookahead)
- **EmbeddingEngine**: Multi-model support (FinBERT, SentenceTransformers)
- **Walk-forward validation**: Proper temporal splits

---

## Known Issues & Technical Debt

### Critical
- [ ] ML strategy validation: Need to run MCPT on XGBoost/LightGBM strategies
- [ ] Document the specific feature leakage issues from mid/small cap analysis

### High Priority
- [ ] DuckDB feature cache implementation (currently features computed fresh each run)
- [ ] Earnings call transcript NLP integration

### Medium Priority
- [ ] HTML report generation from evaluation module
- [ ] Factor exposure analysis integration
- [ ] Combinatorial purged CV for more robust testing

### Low Priority
- [ ] Additional alt data sources (job postings, web traffic, patents)
- [ ] Dark pool data integration

---

## Architecture Decisions

### Why Vectorized Backtesting
- 100x faster than event-driven for simple strategies
- Sufficient for our signal-based approach
- Easy to audit for lookahead bias

### Why MCPT over Traditional Significance Tests
- Distribution-free (no normality assumptions)
- Directly tests trading strategy, not just returns
- Robust to autocorrelation in financial data
- p < 0.05 threshold before any production deployment

### Why Regime-Based Selection
- Analysis of 470+ strategies showed dramatic performance variation by regime
- Momentum goes from +2.48 Sharpe (uptrend) to -1.90 (downtrend)
- Dynamic selection can capture 2-3x better risk-adjusted returns

---

## Performance Baselines

| Benchmark | Sharpe | Notes |
|-----------|--------|-------|
| SPY Buy-and-Hold | ~0.7-0.8 | Long-term average |
| 60/40 Portfolio | ~0.6-0.7 | Traditional allocation |
| Our best validated | 3.14 | bollinger_reversal/QCOM |

---

## Next Development Priorities

1. Validate ML strategies with MCPT
2. Investigate and document mid/small cap feature leakage
3. Implement feature persistence with DuckDB
4. Add earnings call NLP analysis
5. Expand regime analysis to more symbols
