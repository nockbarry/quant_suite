# Project Athena: Hybrid Intelligence Trading System

A trading platform that fuses **statistical alpha generation**, **LLM reasoning**, and **human oversight** for accounts of any size ($200-$25,000+).

---

## The Core Insight

Within algorithmic trading, there exists a largely unexplored middle ground between two dominant paradigms:

### Camp A: Pure Quantitative
Statistical models analyzing price, volume, and technical indicators. Rigorous and systematic, but often blind to the broader context that drives markets.

### Camp B: Pure Discretionary
Human judgment interpreting news, sentiment, and macro conditions. Flexible and contextual, but prone to emotion, bias, and inconsistency.

### Camp C: Hybrid Intelligence (Project Athena)
What if a system could harness the pattern-finding power of statistics, the contextual reasoning of large language models, and the judgment of an informed human? This isn't replacing any single approach but creating something genuinely new: a pipeline where **each layer contributes its unique strength**, and no single point of failure can derail the entire strategy.

---

## Three Intelligence Layers

```
+---------------------------------------------------------------------+
|                    INTELLIGENCE PIPELINE                            |
+---------------------------------------------------------------------+
|                                                                     |
|   STATISTICAL           LLM (Claude)            HUMAN               |
|   ---------------       ---------------         ---------------     |
|   * 50+ features        * Synthesizes           * EOD review        |
|   * Technical             all inputs            * Approve trades    |
|   * Alternative data    * Latent knowledge      * Override          |
|   * ML models           * Documents "why"       * Set rules         |
|                                                                     |
|   "What patterns        "Does this make         "Do I trust         |
|    exist in data?"       sense?"                 this?"             |
+---------------------------------------------------------------------+
```

**Why this works:**
- **Statistics** find patterns humans miss in raw data
- **LLMs** provide context, reasoning, and market intuition humans would apply
- **Human oversight** catches errors both systems might make
- **Full audit trail** of every decision with documented reasoning

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourusername/quant_suite.git
cd quant_suite
pip install -r requirements.txt

# Configure credentials
cp config/credentials.yaml.example config/credentials.yaml
# Edit with your Alpaca API keys

# Run daily workflow with Claude Code
claude /morning-briefing
claude /trade-decision
claude /execute-trades

# Or run statistical pipeline directly
PYTHONPATH=. python scripts/run_daily.py --mode paper
```

---

## Daily Workflow

```
6:30 AM   /morning-briefing    Gather news, portfolio state, alternative data
7:00 AM   /trade-decision      Claude synthesizes and makes BUY/SELL/HOLD decisions
7:30 AM   /execute-trades      Execute approved trades (human approval required)
4:30 PM   /eod-review          Analyze outcomes, update learnings
```

**Key Innovation**: Claude Code IS the decision engine. Statistical models generate signals, but Claude synthesizes research context and applies latent market knowledge to make final trading decisions with documented reasoning.

---

## Output Directory Structure

All outputs are stored in a configurable results directory (default: `~/quant_results`):

```
quant_results/
+-- briefings/              # Morning briefings and daily summaries
+-- decisions/              # Trading decisions with reasoning logs
+-- trades/                 # Trade execution records
+-- trading_logs/           # Detailed session logs
|
+-- comprehensive_research/ # Full research cycle outputs
+-- research_sessions/      # Text research session data
+-- research_reports/       # Analysis reports
+-- strategy_reports/       # Strategy documentation
|
+-- alpha_discovery/        # Alpha scan results
+-- macro_research/         # Geopolitical and macro analysis
+-- regime_reports/         # Market regime classifications
|
+-- validation_reports/     # Strategy validation (MCPT, walk-forward)
+-- critic_reports/         # Safety validation for bias detection
+-- plots/                  # Strategy visualizations
|
+-- promotions/             # Strategy promotion records
+-- paper_trading/          # Paper trading outputs
+-- pdt/                    # PDT compliance tracking
+-- performance_reports/    # Performance analytics
|
+-- scraped_data/           # Alternative data cache
+-- sessions/               # Session-based research data
+-- archive/                # Historical data
```

### Configuring Output Location

Set the environment variable to customize the results directory:

```bash
# Default (uses ~/quant_results)
python scripts/run_trading.py

# Custom location
QUANT_RESULTS_DIR=/data/trading/results python scripts/run_trading.py
```

Or use the PathConfig programmatically:

```python
from src.core.paths import PathConfig, paths

# Use default paths
briefing_dir = paths.briefings
decisions_dir = paths.decisions

# Use custom base directory
custom_paths = PathConfig("/data/my_results")
```

---

## Features

### Alternative Data Sources

| Source | Signals |
|--------|---------|
| Congressional Trades | Cluster buying (Pelosi, committee members) |
| Prediction Markets | Fed policy, recession odds, macro events |
| Expert Sentiment | Inverse Cramer, follow/fade pundits |
| Insider Trading | SEC Form 4 cluster buying |
| Options Flow | Unusual activity, institutional positioning |
| News/Reddit | Sentiment, trending tickers |

### PDT Compliance

For accounts under $25,000:
- Tracks 3 day trades per 5 rolling days
- Enforces 2-day minimum hold for swings
- PDTManager for real-time capacity tracking

### Intraday Trading

- VWAP bounce strategy
- Momentum continuation
- ATR-based stops and targets
- Session phase awareness (opening, power hour)

### Research Framework

- 13 specialized Claude Code agents
- MCPT validation (p < 0.05 required)
- Walk-forward testing
- Critic validation for bias detection

---

## Architecture

```
PRE-MARKET
+----------------------------------------------------------+
|                                                          |
|  Alternative Data     Statistical         Research       |
|  -----------------    ----------          --------       |
|  Congressional        Swing signals       Overnight      |
|  Prediction mkts      Intraday (5m)       news          |
|  Expert sentiment     Technical           Pre-market    |
|  Insider trading      ML models           Portfolio     |
|                                                          |
|                    |                                     |
|                    v                                     |
|           +------------------+                           |
|           | MORNING BRIEFING |                           |
|           | (Structured)     |                           |
|           +--------+---------+                           |
|                    |                                     |
|                    v                                     |
|           +------------------+                           |
|           |  LLM DECISION    |                           |
|           |  * Synthesize    |                           |
|           |  * Reason        |                           |
|           |  * Decide + why  |                           |
|           +--------+---------+                           |
|                    |                                     |
|                    v                                     |
|           +------------------+                           |
|           |   EXECUTION      |                           |
|           |  * Risk check    |                           |
|           |  * PDT check     |                           |
|           |  * Approval      |                           |
|           |  * Submit        |                           |
|           +--------+---------+                           |
|                    |                                     |
|                    v                                     |
|           +------------------+                           |
|           |  LEARNING LOOP   |                           |
|           |  * Track P&L     |                           |
|           |  * What worked   |                           |
|           |  * Update KB     |                           |
|           +------------------+                           |
+----------------------------------------------------------+
```

---

## Claude Code Integration

### Skills

**Daily Trading:**
- `/morning-briefing` - Pre-market research
- `/trade-decision` - LLM decision engine
- `/execute-trades` - Execute with approval
- `/eod-review` - Daily analysis

**Research:**
- `/research`, `/validate`, `/critic`, `/brainstorm`, `/promote`, `/monitor`, `/report`

### Agents (13)

**Research:** research-agent, research-worker-agent, alpha-discovery-agent, hypothesis-generator-agent, brainstorm-agent

**Market Intelligence:** macro-research-agent, news-analyst-agent, regime-detector-agent

**Operations:** critic-agent, monitor-agent, data-acquisition-agent, orchestrator-agent

---

## Validation Requirements

Before production:
- **MCPT p-value < 0.05** (Monte Carlo Permutation Test)
- **Out-of-sample Sharpe > 0.5**
- **Critic validation** (no lookahead bias, overfitting)

```python
from src.evaluation.validation.mcpt import mcpt_test
result = mcpt_test(strategy_returns, benchmark_returns, n_permutations=1000)
print(f"p-value: {result.p_value:.4f}")
```

---

## Trading Rules

| Rule | Value |
|------|-------|
| Max single position | 25% |
| Max sector exposure | 40% |
| Max daily loss | 5% |
| Stop loss | 5-15% |
| PDT day trades | 3 per 5 days |
| Min swing hold | 2 days |

---

## Documentation

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | Claude Code reference |
| `docs/EVALUATION_API.md` | Backtesting, validation |
| `docs/ALPHA_DISCOVERY.md` | Alternative data |
| `docs/TRADING_GUIDE.md` | User guide |
| `DEVLOG.md` | Development log |
| `RESEARCH_LOG.md` | Research findings |

---

## License

MIT
