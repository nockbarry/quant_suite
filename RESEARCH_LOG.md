# Quant Suite Research Log

**Purpose**: Track research findings, validated results, and flagged issues
**Created**: 2026-01-04
**Last Updated**: 2026-01-04

---

## Validated Results (Production Ready)

These strategies passed MCPT validation (p < 0.05) with out-of-sample Sharpe > 0.5:

| Strategy | Symbol | Sharpe | p-value | Validated Date | Notes |
|----------|--------|--------|---------|----------------|-------|
| bollinger_reversal | QCOM | 3.14 | 0.007 | 2026-01-03 | **Top performer** |
| bollinger_reversal | MU | 2.93 | 0.007 | 2026-01-03 | Semiconductor |
| bollinger_reversal | MRVL | 2.71 | 0.017 | 2026-01-03 | Semiconductor |
| bollinger_reversal | IWM | 2.34 | 0.040 | 2026-01-03 | Small-cap ETF |
| momentum | AMD | 2.11 | 0.047 | 2026-01-03 | High-beta tech |
| insider_technical | QQQ | 1.23 | 0.000 | 2026-01-03 | **Highest significance** |
| rsi_reversal | MSFT | 0.88 | 0.031 | 2026-01-03 | Large cap works |
| rsi_reversal | SPY | 0.72 | 0.042 | 2026-01-03 | Index reversal |

---

## Flagged Results (Require Validation)

### ML Strategies - MCPT Not Documented

| Strategy | Symbol | Reported Sharpe | Issue |
|----------|--------|-----------------|-------|
| xgboost_classifier | QCOM | 1.77 | No MCPT p-value in reports |
| lightgbm_classifier | NVDA | 1.52 | No MCPT p-value in reports |
| random_forest | AMD | 1.34 | No MCPT p-value in reports |

**Action Required**: Run MCPT validation on ML strategies before production use.

### Borderline Significance

| Strategy | Symbol | Sharpe | p-value | Issue |
|----------|--------|--------|---------|-------|
| multi_signal | AMD | 1.45 | 0.045 | At p=0.05 threshold |

**Recommendation**: Treat as exploratory, not production-ready.

### Feature Leakage Concerns

**Historical Issue**: User mentioned mid/small cap analysis had feature leakage problems, but specifics were not documented in the result files.

**What We Know**:
- Leakage audit on 2026-01-03 showed all features passed with "low" lookahead risk
- Feature correlations with target all < 0.03 (acceptable)
- All features properly use `.shift(1)` for lagging

**What's Missing**:
- Specific strategies/symbols that had leakage
- What the leakage pattern was
- How it was fixed

**Recommendation**: If you encounter unexpectedly high Sharpe ratios (>3.0) without clear explanation, rerun the leakage audit.

---

## Regime-Based Strategy Selection Framework

### Key Finding (2026-01-03)
Analysis of 470+ strategy/symbol combinations revealed:

| Market Segment | Strategies Beating Buy-and-Hold | Win Rate |
|----------------|--------------------------------|----------|
| Large Cap (SPY, QQQ, AAPL) | 20 | 3.8% |
| Mid/Small Cap (CRWD, PLTR, etc.) | 70 | 14.9% |

**Conclusion**: Large caps are too efficient. Focus alpha-seeking on mid/small caps.

### Regime-Strategy Performance Matrix

| Strategy | High Vol + Up | High Vol + Down | Low Vol + Up | Low Vol + Down |
|----------|--------------|-----------------|--------------|----------------|
| RSI_14_30 | **1.54** | 0.70 | 1.05 | -0.18 |
| Mean_Rev_20_2.0 | **1.08** | 0.84 | 0.38 | 0.62 |
| Momentum_20 | 0.31 | **-1.90** | **2.48** | 1.67 |
| Breakout_10 | **1.79** | **-0.60** | 0.88 | 0.90 |

### Strategy Selection Rules

| Regime | Use | Avoid |
|--------|-----|-------|
| HIGH_VOL + UPTREND | RSI, Breakout, Mean-Rev | - |
| HIGH_VOL + DOWNTREND | RSI, Mean-Rev only | Momentum, Breakout |
| LOW_VOL + UPTREND | Momentum | RSI |
| LOW_VOL + DOWNTREND | REDUCE EXPOSURE | All aggressive |

---

## Knowledge Base Patterns

From `workflows/research/knowledge_base.py`:

| Pattern | Confidence | Successes | Avg p-value |
|---------|------------|-----------|-------------|
| bollinger_reversal_works | 95% | 27 | 0.019 |
| rsi_reversal_works | 70% | 4 | 0.035 |
| momentum_works | 60% | 2 | 0.046 |
| semiconductors_mean_revert | 85% | 12 | 0.022 |

---

## Failed Hypotheses (Do Not Repeat)

| Hypothesis | Tested | Result | Reason |
|------------|--------|--------|--------|
| Momentum on large caps | 2026-01-02 | Failed | Too efficient, quickly arbitraged |
| Breakout in downtrend | 2026-01-03 | Failed | False breakouts, Sharpe < 0 |
| RSI on low-vol stocks | 2026-01-02 | Failed | Not enough price movement |
| Short-term momentum (<5d) | 2026-01-03 | Failed | Transaction costs eat alpha |

---

## Alternative Data Signals

### Short Interest (as of 2026-01-03)

| Symbol | Short % Float | Days to Cover | Squeeze Candidate |
|--------|--------------|---------------|-------------------|
| GME | 16.6% | 10.2 | **Yes** |
| AMC | 12.3% | 8.4 | Maybe |

### Google Trends Retail Attention

| Sector | Attention Z-Score | Signal |
|--------|------------------|--------|
| Tech Mega | -0.8 | Below average (contrarian bullish) |
| Semiconductors | -0.3 | Normal |
| Meme Stocks | +1.2 | Above average (contrarian bearish) |

---

## Top Performing Symbol/Strategy Combinations (All Time)

Ranked by Sharpe ratio (validated only):

| Rank | Strategy/Symbol | Sharpe | Outperformance vs B&H |
|------|-----------------|--------|----------------------|
| 1 | bollinger_reversal/QCOM | 3.14 | +89.7% |
| 2 | bollinger_reversal/MU | 2.93 | +82.1% |
| 3 | bollinger_reversal/MRVL | 2.71 | +76.3% |
| 4 | bollinger_reversal/IWM | 2.34 | +61.2% |
| 5 | momentum/AMD | 2.11 | +54.8% |

---

## Research Leads (Priority Queue)

### High Priority
1. **Extend bollinger_reversal to DIA** - Mean reversion may work on index ETFs
2. **Test mean reversion on high-vol stocks** - AMZN, META, NVDA candidates
3. **Validate ML strategies** - Run MCPT on XGBoost, LightGBM

### Medium Priority
4. **Expand to financials** - JPM, GS, V, MA untested
5. **Test RSI variants** - RSI_7 vs RSI_14 vs RSI_21 comparison
6. **Healthcare sector** - JNJ, UNH, PFE for defensive plays

### Low Priority
7. **Crypto strategies** - Higher volatility may suit mean reversion
8. **Options strategies** - Covered calls on high-vol positions
9. **Pairs trading** - NVDA/AMD, GOOGL/META spreads

---

## Research Protocol Checklist

Before marking any result as "validated":

- [ ] MCPT p-value < 0.05
- [ ] Out-of-sample Sharpe > 0.5
- [ ] Walk-forward validation completed
- [ ] Leakage audit passed (all features lagged)
- [ ] Regime performance analyzed
- [ ] PDT holding period optimized

---

## Session Insights Archive

### 2026-01-04
- Consolidated all research findings into this log
- Flagged ML strategies needing validation
- Updated regime framework documentation

### 2026-01-03
- Discovered bollinger_reversal edge on semiconductors
- Validated 5 production-ready strategies
- Built regime-based strategy selection framework
- Deployed 10 Claude Code agents

### 2026-01-02
- Built text research framework
- Implemented point-in-time safe embeddings
- Created 7 text features

---

## Workflow Integration Status

The evaluation module functions are now integrated into the main workflows:

### Completed Integrations

| Workflow | Functions Integrated | Status |
|----------|---------------------|--------|
| **ComprehensiveResearcher** | `BootstrapCI`, `reality_check`, `detect_regimes`, `evaluate_by_regime`, `get_current_regime`, all metrics | Complete |
| **validate_strategy.py** | `BootstrapCI`, `detect_regimes`, `evaluate_by_regime`, `get_current_regime`, `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, `max_drawdown`, `win_rate` | Complete |
| **research_cycle.py** | `reality_check`, `stepwise_spa`, `detect_regimes`, `get_current_regime` | Complete |

### Remaining Integration Opportunities

| Function | Module | Use Case | Priority |
|----------|--------|----------|----------|
| `combinatorial_purged_cv()` | purged_cv | More robust cross-validation | Medium |
| `FactorModel` | attribution | Factor exposure analysis | Low |
| `generate_backtest_report()` | reporting | Automated HTML reports | Low |

See `docs/EVALUATION_API.md` for detailed usage examples.

---

## Appendix: Data Sources

| Source | Type | Update Frequency | Quality |
|--------|------|------------------|---------|
| yfinance | Price/Volume | Real-time | High |
| SEC EDGAR | Filings | Daily | High |
| Google Trends | Retail Attention | Daily | Medium |
| Short Interest | Squeeze Data | Bi-weekly | Medium |
| News RSS | Headlines | Continuous | Variable |
