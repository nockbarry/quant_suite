# Trading Suite: Budget Edition
## Optimized for Small Capital ($200-$2,000)

---

## Executive Summary

This revision addresses the reality of starting with hundreds of dollars. The constraints are significant but not insurmountable—we need to be strategic about broker choice, trading frequency, and data sources.

---

## 1. Critical Constraint: The PDT Rule

### The Problem
The **Pattern Day Trader (PDT) rule** is your biggest obstacle. If you have under $25,000 in a **margin account**, you're limited to **3 day trades per 5 business days**. A "day trade" = buying and selling the same security on the same day.

### Good News
FINRA is actively working on relaxing this rule—potentially dropping the minimum to $2,000. But as of now, it's still $25,000.

### Workarounds for Small Accounts

| Strategy | How It Works | Pros | Cons |
|----------|--------------|------|------|
| **Cash Account** | PDT doesn't apply. Trade as much as you want with *settled* funds | No day trade limit | T+2 settlement (funds locked 2 days after sell) |
| **Swing Trading** | Hold positions 2+ days | No PDT issues, less stressful | Overnight risk, fewer opportunities |
| **Multiple Brokers** | 3 day trades per account | 6-9 day trades/week with 2-3 accounts | Capital split, complexity |
| **Futures/Forex** | PDT doesn't apply (different regulator) | Unlimited trades | Higher risk, different skills needed |

### Recommended Approach for Your Scale

**Primary: Swing Trading (2-10 day holds)**

This is the optimal strategy for small capital because:
1. No PDT restrictions
2. Overnight moves can generate larger profits than intraday
3. Lower transaction frequency = less execution slippage eating your capital
4. More time for the agent to research and validate signals
5. Compounding works better with fewer, higher-conviction trades

**Secondary: Cash Account Day Trading (limited)**

Use a cash account for occasional day trades when high-conviction setups appear. Just track your settled cash carefully to avoid Good Faith Violations.

---

## 2. Broker Comparison for Small Accounts

### Winner: **Alpaca**

| Feature | Alpaca | Interactive Brokers | Robinhood |
|---------|--------|---------------------|-----------|
| **Minimum Deposit** | $0 | $0 | $0 |
| **Commission** | $0 stocks/ETFs | $0 (Lite) or ~$0.005/share (Pro) | $0 |
| **API Quality** | Excellent (built for algo trading) | Good but complex | Limited |
| **Paper Trading** | Free, full-featured | Free | None |
| **Fractional Shares** | Yes | Yes | Yes |
| **Real-time Data** | Free with funded account | Extra cost | Delayed |
| **PDT Handling** | Standard | Standard | Standard |
| **Best For** | Automated trading | Advanced traders, global markets | Manual mobile trading |

### Why Alpaca for Your Project

1. **API-First Design**: Built specifically for algorithmic trading—clean REST API, Python SDK, WebSocket streaming
2. **Free Paper Trading**: Test your strategies risk-free with realistic execution
3. **Commission-Free**: Critical when your account is small (commissions would destroy returns)
4. **Free Market Data**: Polygon integration included for funded accounts
5. **No Minimum**: Start with whatever you have
6. **Fractional Shares**: Buy $50 of a $500 stock (essential for small accounts)

### Why NOT Interactive Brokers (for now)

Interactive Brokers is the professional choice for larger accounts because:
- Lower margin rates
- Access to global markets (not just US)
- Options, futures, forex, bonds, etc.
- Better execution quality on large orders
- More sophisticated order types

**But for hundreds of dollars:**
- Their interface is complex and overkill
- API has a steeper learning curve
- No significant advantage at your scale
- Alpaca's simplicity is a feature, not a bug

**Recommendation**: Start with Alpaca. Graduate to IBKR when your account exceeds $10,000 and you need options/futures.

---

## 3. Trading Frequency Analysis

### Why Daily/Swing is Better Than Intraday for Small Accounts

| Factor | Intraday | Daily/Swing |
|--------|----------|-------------|
| **PDT Impact** | Severe limitation | No issue |
| **Data Costs** | Need real-time (expensive) | EOD is free |
| **Compute Needs** | Must run during market hours | Can run overnight |
| **Spread Cost** | Hurts every trade | Amortized over days |
| **Signal Quality** | More noise, less edge | Cleaner signals |
| **Agent Workload** | Real-time pressure | Thoughtful analysis |
| **Win Percentage Needed** | Higher (many small bets) | Lower (fewer, larger bets) |

### Recommended Frequencies

| Strategy Type | Holding Period | Rebalance Frequency | Why |
|---------------|----------------|---------------------|-----|
| **Momentum** | 1-4 weeks | Weekly | Let trends develop |
| **Mean Reversion** | 2-5 days | Daily | Capture oversold bounces |
| **Sentiment** | 1-3 days | Daily | News impact is fast but not instant |
| **Value/Quality** | 1-3 months | Monthly | Fundamentals move slowly |

### Position Sizing for Small Accounts

With $500 capital, example allocation:
```
Max positions: 5-8 (diversification without over-dilution)
Position size: $60-100 each
Max single position: 20% of portfolio ($100)
Cash reserve: 10-20% for opportunities
```

This means fractional shares are essential—you can't buy full shares of most quality stocks.

---

## 4. Free Data Sources

### Tier 1: Essential (All Free)

| Source | Data Type | API | Rate Limits | Notes |
|--------|-----------|-----|-------------|-------|
| **yfinance** | Prices, fundamentals, options | Python library | Unofficial, can break | Most popular, use as backup |
| **Alpha Vantage** | Prices, forex, crypto, indicators | REST | 5 req/min free | Good for technical indicators |
| **Alpaca** | Real-time prices (if funded) | REST + WebSocket | Generous | Comes with your broker |
| **FRED** | Economic data | REST | Generous | Federal Reserve data |
| **SEC EDGAR** | Filings, insider trades | REST | No limit | Direct from SEC |
| **Finnhub** | News, sentiment, prices | REST | 60 req/min free | Good sentiment data |

### Tier 2: Alternative Data (Free)

| Source | Data Type | How to Access | Signal Type |
|--------|-----------|---------------|-------------|
| **Reddit API** | r/wallstreetbets, r/stocks | PRAW library | Retail sentiment (often contrarian) |
| **ApeWisdom API** | Reddit mention aggregation | REST | Trending tickers |
| **Google Trends** | Search interest | pytrends library | Retail attention |
| **SEC EDGAR** | Form 4 (insider buys/sells) | REST | Smart money |
| **Finviz** | Screener, news | Scraping (careful) | Technical signals |
| **Earnings Whispers** | Earnings calendar | Scraping | Event timing |
| **OpenInsider** | Insider trading aggregation | Scraping | Smart money |

### Tier 3: Fundamental Data (Free Tiers)

| Source | Coverage | Free Tier | Notes |
|--------|----------|-----------|-------|
| **Financial Modeling Prep** | Financials, ratios | 250 req/day | Good quality |
| **Polygon.io** | Prices, news, reference | Limited free | Premium with Alpaca |
| **IEX Cloud** | US stocks, news | Pay-as-you-go | ~$9/month for light use |
| **Tiingo** | News, prices | 500 req/hour | Good news API |
| **Quandl/Nasdaq** | Various | Some free datasets | Patchy coverage |

### Data Source Priority for Budget Build

```
Phase 1: MVP (Cost: $0)
├── Prices: yfinance + Alpha Vantage backup
├── Fundamentals: Financial Modeling Prep free tier
├── Sentiment: Reddit API + ApeWisdom
├── Economic: FRED
└── Insider: SEC EDGAR Form 4

Phase 2: Enhancement (Cost: $0-20/month)
├── Prices: Alpaca real-time (free with funded account)
├── News: Finnhub + Tiingo
├── Screener: Finviz scraping
└── Options flow: Manual monitoring (unusual whales alternatives)

Phase 3: Scale (Cost: $50-100/month)
├── Professional data: Polygon or IEX Cloud paid
├── Alternative data: Quiver Quantitative
└── Backtesting: QuantConnect cloud
```

---

## 5. Revised Architecture for Budget Build

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE CODE ORCHESTRATOR                     │
│              (Runs locally, controls everything)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  DATA LAYER    │  │  RESEARCH      │  │  EXECUTION     │    │
│  │  (Free APIs)   │  │  (Local)       │  │  (Alpaca)      │    │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘    │
│          │                   │                   │              │
│          ▼                   ▼                   ▼              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    LOCAL SQLite/DuckDB                    │  │
│  │         (Features, signals, trades, research docs)        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Why Local-First

- **Cost**: $0 infrastructure (no cloud needed initially)
- **Speed**: No network latency for backtests
- **Privacy**: Your strategies stay on your machine
- **Simplicity**: One machine, one codebase

### Recommended Stack

```
Language: Python 3.11+
Database: DuckDB (fast analytical queries, single file)
Broker API: alpaca-py
Data: yfinance, fredapi, praw (Reddit), requests
ML: scikit-learn, lightgbm (no GPU needed)
Backtesting: vectorbt or custom
Scheduling: APScheduler or cron
Agent Framework: Claude Code with tool use
```

---

## 6. Strategy Recommendations for Small Capital

### Strategies That Work at Small Scale

| Strategy | Why It Works | Example |
|----------|--------------|---------|
| **Momentum (weekly)** | Strong empirical evidence, scales down well | Buy top 5 momentum stocks weekly |
| **Oversold Bounce** | Mean reversion in quality stocks | RSI < 30 + quality filters |
| **Earnings Momentum** | Post-earnings drift is well-documented | Buy beats, sell misses |
| **Insider Following** | Legal edge, low frequency | Follow cluster buys |
| **Sentiment Contrarian** | Reddit extremes predict reversals | Fade WSB euphoria |

### Strategies to AVOID at Small Scale

| Strategy | Why It Fails | Issue |
|----------|--------------|-------|
| **High-frequency** | Need co-location, special data | Millisecond latency matters |
| **Market Making** | Need capital for inventory | Can't handle adverse selection |
| **Pairs Trading** | Need many pairs for diversification | Capital spread too thin |
| **Options Selling** | Need margin, capital for assignment | Too risky at small size |
| **Leveraged ETFs** | Decay destroys long-term holds | Math works against you |

### Budget Picks Discovery (Your "Edge")

This is where your alternative data focus can shine:

```python
class BudgetPickFinder:
    """
    Find small/mid caps with positive alternative signals
    but no price momentum yet.
    """
    
    def score_opportunity(self, symbol):
        scores = {}
        
        # 1. Price is flat (opportunity not priced in)
        momentum_60d = self.get_momentum(symbol, 60)
        scores['price_flat'] = 1 if abs(momentum_60d) < 0.10 else 0
        
        # 2. Reddit mentions increasing (retail discovery)
        reddit_trend = self.get_reddit_trend(symbol)
        scores['reddit_rising'] = 1 if reddit_trend > 0 else 0
        
        # 3. Insider buying (smart money)
        insider_signal = self.get_insider_signal(symbol)
        scores['insider_buying'] = 1 if insider_signal > 0 else 0
        
        # 4. Low analyst coverage (inefficient)
        analyst_count = self.get_analyst_count(symbol)
        scores['under_covered'] = 1 if analyst_count < 5 else 0
        
        # 5. Reasonable valuation
        pe_rank = self.get_pe_percentile(symbol)
        scores['not_expensive'] = 1 if pe_rank < 0.7 else 0
        
        # 6. Positive earnings surprise (recent)
        earnings_surprise = self.get_earnings_surprise(symbol)
        scores['beat_earnings'] = 1 if earnings_surprise > 0.05 else 0
        
        return sum(scores.values()) / len(scores), scores
```

---

## 7. Validation Framework (Simplified for Speed)

### Minimum Viable Validation

Since you're starting small, we don't need the full institutional validation suite. But we DO need:

```python
class SimpleValidator:
    """
    Minimum validation to avoid obvious overfitting.
    """
    
    def validate_strategy(self, strategy, data):
        results = {}
        
        # 1. Walk-forward test (REQUIRED)
        # Train on past, test on future, repeat
        wf_results = self.walk_forward_test(
            strategy, data,
            train_window=252,  # 1 year
            test_window=63,    # 3 months
            step=21            # Monthly refit
        )
        results['sharpe_oos'] = wf_results['sharpe']
        
        # 2. Check for overfitting
        # If in-sample Sharpe >> out-of-sample, it's overfit
        results['overfit_ratio'] = (
            wf_results['sharpe_in_sample'] / 
            max(wf_results['sharpe_out_sample'], 0.01)
        )
        results['likely_overfit'] = results['overfit_ratio'] > 2.0
        
        # 3. Minimum sample size
        results['n_trades'] = wf_results['n_trades']
        results['sufficient_trades'] = results['n_trades'] > 30
        
        # 4. Reality checks
        results['realistic_turnover'] = wf_results['turnover'] < 50  # <50x/year
        results['realistic_sharpe'] = results['sharpe_oos'] < 3.0    # >3 is suspect
        
        # 5. Drawdown tolerance
        results['max_drawdown'] = wf_results['max_drawdown']
        results['acceptable_dd'] = results['max_drawdown'] < 0.25  # <25%
        
        # PASS/FAIL
        results['valid'] = (
            results['sharpe_oos'] > 0.5 and
            not results['likely_overfit'] and
            results['sufficient_trades'] and
            results['realistic_turnover'] and
            results['realistic_sharpe'] and
            results['acceptable_dd']
        )
        
        return results
```

### Minimum Performance Thresholds

| Metric | Minimum | Target | Notes |
|--------|---------|--------|-------|
| Sharpe Ratio (OOS) | 0.5 | 1.0+ | Below 0.5 is noise |
| Win Rate | 45% | 55%+ | Combined with good R:R |
| Max Drawdown | <30% | <15% | You'll panic at 30%+ |
| Trades per Year | 30+ | 50-200 | Statistical significance |
| Profit Factor | >1.2 | >1.5 | Gross profit / gross loss |

---

## 8. Simplified Phased Implementation

### Phase 1: Foundation (Week 1-2)

**Goal**: Get data flowing and run first backtest

```
Tasks:
□ Set up Python environment
□ Create Alpaca paper trading account
□ Build data ingestion for yfinance + Alpha Vantage
□ Implement basic momentum strategy
□ Run simple backtest (no walk-forward yet)
□ Set up SQLite/DuckDB for data storage

Deliverable: Working backtest of 12-1 momentum strategy
```

### Phase 2: Validation (Week 3-4)

**Goal**: Add proper validation to avoid overfitting

```
Tasks:
□ Implement walk-forward testing
□ Add basic performance metrics
□ Backtest 3-5 simple strategies
□ Compare results, identify best candidates
□ Document findings in research KB

Deliverable: Validated strategy with OOS Sharpe > 0.5
```

### Phase 3: Alternative Data (Week 5-6)

**Goal**: Add sentiment and insider signals

```
Tasks:
□ Set up Reddit API access (PRAW)
□ Build sentiment scoring for r/wallstreetbets, r/stocks
□ Parse SEC EDGAR for insider transactions
□ Create "budget picks" discovery module
□ Test alternative signals in backtest

Deliverable: Alternative data features generating signal
```

### Phase 4: Paper Trading (Week 7-8)

**Goal**: Run live paper trading

```
Tasks:
□ Build Alpaca integration for order execution
□ Implement position sizing for small account
□ Set up daily signal generation
□ Run paper trading for 2+ weeks
□ Compare paper results to backtest expectations

Deliverable: Paper trading running autonomously
```

### Phase 5: Live Trading (Week 9+)

**Goal**: Go live with real (small) money

```
Tasks:
□ Fund Alpaca account ($200-500)
□ Implement risk limits and alerts
□ Start with 50% of intended position sizes
□ Monitor daily, document everything
□ Iterate based on results

Deliverable: Live trading with positive expectancy
```

---

## 9. Risk Management for Small Accounts

### Hard Rules

```python
class SmallAccountRiskManager:
    def __init__(self, account_size):
        self.account_size = account_size
        
        # Position limits
        self.max_position_pct = 0.20      # 20% max in one stock
        self.max_positions = 8            # Diversification
        self.min_position = 25.0          # Don't bother with <$25
        
        # Loss limits
        self.daily_loss_limit = 0.05      # Stop trading at -5% day
        self.weekly_loss_limit = 0.10     # Stop trading at -10% week
        self.max_drawdown = 0.25          # Reassess strategy at -25%
        
    def check_trade(self, order):
        position_size = order.quantity * order.price
        position_pct = position_size / self.account_size
        
        if position_pct > self.max_position_pct:
            return False, f"Position too large: {position_pct:.1%}"
        
        if position_size < self.min_position:
            return False, f"Position too small: ${position_size:.2f}"
            
        return True, "OK"
```

### What to Do When Losing

| Drawdown | Action |
|----------|--------|
| 0-10% | Normal volatility, continue |
| 10-15% | Reduce position sizes by 50% |
| 15-25% | Stop trading, review strategy |
| 25%+ | Stop trading, full reassessment |

---

## 10. Open Questions Resolved

| Question | Answer |
|----------|--------|
| **Starting capital** | $200-2000 |
| **Trading frequency** | Daily signals, swing holding (2-10 days) |
| **Maximum drawdown** | 25% (reassess strategy) |
| **Broker** | Alpaca (free, API-first, fractional shares) |
| **Alternative data budget** | $0 initially, maybe $20-50/month later |
| **Automation level** | High automation, daily human review |

---

## 11. Realistic Expectations

### What's Possible

With a well-validated strategy and $500 starting capital:
- **Annual return target**: 15-30% (beating S&P)
- **Monthly return**: 1-3% average (high variance)
- **Sharpe ratio**: 0.8-1.5 (good but not exceptional)
- **Drawdowns**: 10-20% expected at some point

### What's NOT Possible

- Turning $500 into $50,000 in a year (that's 100x)
- Consistent monthly income (variance too high)
- Competing with HFT firms on speed
- Risk-free returns

### The Real Goal

This is a **research and validation project** first. The goal is to:
1. Build infrastructure that scales
2. Validate that the system can identify real edges
3. Document what works and what doesn't
4. Grow capital gradually as confidence increases

If after 6 months your validated strategies show consistent edge, you can:
- Add more capital
- Use multiple strategies
- Potentially attract outside capital

---

## 12. Next Steps

1. **Review this document** - Any questions or changes?
2. **Set up development environment** - Python, DuckDB, APIs
3. **Create Alpaca paper account** - Start testing immediately
4. **Begin Phase 1** - Get first backtest running

Ready to start building?
