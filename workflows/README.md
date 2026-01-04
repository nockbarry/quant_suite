# Quant Suite Workflows

This directory contains reusable workflows for LLM-driven strategy development.

## Quick Start

```bash
# Run the full strategy development workflow
python3 workflows/snippets/full_workflow.py

# Or import and customize:
python3 -c "
from workflows.snippets.full_workflow import run_full_workflow
results = run_full_workflow(
    symbols=['QQQ', 'SPY', 'META', 'NVDA'],
    days=90
)
"
```

## Directory Structure

```
workflows/
├── README.md                           # This file
├── llm_strategy_development.md         # Detailed workflow documentation
├── snippets/
│   └── full_workflow.py                # Complete executable workflow
└── session_results/
    └── YYYY-MM-DD_strategy_test.md     # Session results logs
```

## Workflow Steps

1. **Data Acquisition** - Load/generate market data for universe
2. **Regime Detection** - Classify trend and volatility regime
3. **Strategy Testing** - Backtest 15+ strategy variants
4. **Performance Ranking** - Sort by Sharpe ratio
5. **Optimization** - Grid search for best parameters
6. **Statistical Validation** - Significance testing
7. **Recommendations** - Filtered, significant strategies

## Available Strategies

| Type | Strategy | Description |
|------|----------|-------------|
| Trend | SMA_5_20 | Fast SMA crossover |
| Trend | SMA_10_30 | Medium SMA crossover |
| Trend | SMA_20_50 | Slow SMA crossover |
| Trend | Breakout_10/20/40 | Donchian channel |
| Trend | TrendFollow | ADX-based |
| Mean Rev | RSI_7/14 | RSI oversold/overbought |
| Mean Rev | Bollinger_10/20 | Bollinger band reversion |
| Momentum | Momentum_20/60 | Price momentum |
| Momentum | DualMom_60 | Absolute momentum |
| Volatility | VolBreakout | ATR expansion |

## Regime-Strategy Matching

| Market Regime | Best Strategies |
|---------------|-----------------|
| Strong Uptrend | Momentum_20, Breakout_20 |
| Uptrend | SMA_5_20, SMA_10_30 |
| Sideways | Bollinger_20, RSI_14 |
| Downtrend | Inverse/short strategies |
| High Volatility | VolBreakout, wider stops |

## For LLM Agents

When starting a strategy development session:

1. Read `workflows/llm_strategy_development.md` for detailed context
2. Run `python3 workflows/snippets/full_workflow.py` for baseline
3. Save results to `workflows/session_results/YYYY-MM-DD_*.md`
4. Customize by modifying parameters in `full_workflow.py`

## Key Files Reference

- **Workflow Doc:** `workflows/llm_strategy_development.md`
- **Executable:** `workflows/snippets/full_workflow.py`
- **Latest Results:** Check `workflows/session_results/`
