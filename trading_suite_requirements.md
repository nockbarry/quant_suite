# Trading Model & Strategy Testing Suite
## Comprehensive Requirements Specification

---

## 1. Executive Summary

This document specifies requirements for an automated trading research, backtesting, and execution platform. The system will be orchestrated primarily by Claude Code and sub-agents, with human oversight at critical decision points.

**Core Philosophy:**
- Simulate a quantitative trading firm's research and execution workflow
- Prioritize statistical rigor and avoiding overfitting
- Automate research iteration while maintaining auditability
- Support both high-volume mainstream picks and "budget" alpha discovery

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATION LAYER                               │
│                    (Claude Code + Sub-Agents)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │    DATA      │  │   FEATURE    │  │   STRATEGY   │  │  EXECUTION   │ │
│  │  INGESTION   │→→│  ENGINEERING │→→│   RESEARCH   │→→│   ENGINE     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│         ↓                 ↓                 ↓                 ↓          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                     RESEARCH KNOWLEDGE BASE                          ││
│  │            (Documentation, Results, Audit Trail)                     ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Module Specifications

### 3.1 Asset Universe Management

#### 3.1.1 Symbol Categorization System

**Supported Asset Classes:**
- Equities (common stock, preferred stock, ADRs)
- ETFs (equity, bond, commodity, sector, thematic, leveraged/inverse)
- Options (calls, puts, spreads, exotics)
- Futures (index, commodity, currency, interest rate)
- Forex pairs
- Crypto (spot, perpetuals) — if desired

**Categorization Dimensions:**
| Dimension | Examples | Purpose |
|-----------|----------|---------|
| Sector/Industry | GICS, SIC codes, custom | Sector rotation strategies |
| Market Cap | Mega, Large, Mid, Small, Micro, Nano | Liquidity/risk profiling |
| Geography | US, Developed ex-US, EM, Frontier | Regional exposure |
| Style | Value, Growth, Blend, Momentum | Factor alignment |
| Liquidity Tier | T1 (>$1B daily), T2, T3, Illiquid | Execution feasibility |
| Volatility Regime | Low, Medium, High, Crisis | Risk management |
| Dividend Profile | Growth, Income, Non-paying | Income strategies |
| Options Liquidity | Highly liquid, Liquid, Sparse, None | Derivatives strategies |

**Dynamic Categorization:**
- Categories should update based on rolling metrics (e.g., 20-day ADV for liquidity)
- Support for custom taxonomies defined by research agents
- Hierarchical tagging (e.g., Tech → Semiconductors → Memory)

**Universe Construction:**
```python
# Example universe definition
universe = Universe(
    base="US_EQUITIES",
    filters=[
        MarketCapFilter(min=1e9),          # >$1B market cap
        LiquidityFilter(min_adv=1e6),      # >$1M avg daily volume
        PriceFilter(min=5.0),              # >$5 share price
        ListingAgeFilter(min_days=252),    # Listed >1 year
    ],
    exclusions=["OTC", "ADR", "SPAC"],
    rebalance_frequency="monthly"
)
```

#### 3.1.2 Data Requirements per Asset Class

| Asset Class | Required Data | Update Frequency |
|-------------|---------------|------------------|
| Equities | OHLCV, adjustments, fundamentals, corporate actions | Daily EOD + 15min delayed |
| ETFs | OHLCV, holdings, NAV, premium/discount | Daily EOD |
| Options | Greeks, IV surface, open interest, volume | Real-time during market |
| Futures | OHLCV, open interest, roll dates, basis | Daily + intraday |

---

### 3.2 Feature Engineering Pipeline

#### 3.2.1 Feature Categories

**Price-Derived Features:**
```
Technical Indicators:
├── Trend: SMA, EMA, MACD, ADX, Aroon, Parabolic SAR
├── Momentum: RSI, Stochastic, Williams %R, CCI, ROC
├── Volatility: ATR, Bollinger Bands, Keltner Channels, Historical Vol
├── Volume: OBV, VWAP, A/D Line, Chaikin Money Flow
└── Pattern Recognition: Candlestick patterns, chart patterns (algorithmic)

Statistical Features:
├── Returns: Log returns, arithmetic returns (1d, 5d, 21d, 63d, 252d)
├── Volatility: Realized vol, Parkinson, Garman-Klass, Yang-Zhang
├── Distribution: Skewness, kurtosis, tail risk metrics
├── Correlation: Rolling correlations to indices, sectors, factors
└── Regime: Hidden Markov Model states, breakout detection
```

**Fundamental Features:**
```
Valuation:
├── P/E, Forward P/E, PEG, P/B, P/S, EV/EBITDA, EV/Revenue
├── FCF Yield, Earnings Yield, Dividend Yield
└── Relative valuation vs sector/history

Quality:
├── ROE, ROA, ROIC, Gross Margin, Operating Margin
├── Debt/Equity, Interest Coverage, Current Ratio
├── Altman Z-Score, Piotroski F-Score, Beneish M-Score
└── Accruals, Earnings Quality metrics

Growth:
├── Revenue growth (YoY, QoQ, 3Y CAGR)
├── Earnings growth, EPS revisions
└── Guidance vs consensus
```

**Alternative Data Features:**
```
Sentiment:
├── News sentiment (aggregated, source-weighted)
├── Social media sentiment (Twitter/X, Reddit, StockTwits)
├── Earnings call sentiment (NLP on transcripts)
├── Analyst sentiment (upgrade/downgrade velocity)
└── Insider sentiment (Form 4 analysis)

Web/Alternative:
├── Web traffic trends (SimilarWeb, etc.)
├── App download trends
├── Job postings velocity
├── Patent filings
├── Satellite imagery derived (parking lots, shipping)
├── Credit card transaction trends
└── Search trends (Google Trends)

Market Microstructure:
├── Bid-ask spread dynamics
├── Order flow imbalance
├── Dark pool activity
├── Options flow (put/call ratios, unusual activity)
└── Short interest, days to cover
```

#### 3.2.2 Feature Engineering Principles

**CRITICAL: Preventing Future Data Leakage**

```python
class FeatureEngineer:
    """
    All features must be calculated using ONLY information
    available at the time of prediction.
    """
    
    def calculate_feature(self, data, as_of_date):
        """
        Parameters:
        - data: Historical data up to but NOT including as_of_date
        - as_of_date: The date we're making predictions FOR
        
        Key Rules:
        1. Use only data with timestamp < as_of_date
        2. Account for reporting lags (e.g., 10-K filed ~60 days after quarter end)
        3. Point-in-time fundamentals (what was known WHEN)
        4. No future price data in any calculation
        5. No survivorship bias in universe construction
        """
        pass
```

**Lag Requirements by Data Type:**
| Data Type | Typical Lag | Implementation |
|-----------|-------------|----------------|
| Price/Volume | T+0 (EOD) | Available after market close |
| Fundamentals | 45-90 days | Use filing date, not period end |
| News | T+0 | Timestamp must precede prediction |
| Analyst Estimates | T+0 | Use revision timestamp |
| Economic Data | Varies | Account for revision vintages |

**Feature Standardization:**
```python
# Features should be standardized to enable cross-sectional comparison
# Use rolling windows to avoid look-ahead bias

def standardize_feature(feature_series, lookback=252):
    """
    Cross-sectional z-score using ONLY historical data.
    """
    rolling_mean = feature_series.rolling(lookback).mean()
    rolling_std = feature_series.rolling(lookback).std()
    return (feature_series - rolling_mean) / rolling_std
```

#### 3.2.3 Feature Store Architecture

```
feature_store/
├── raw/                          # Immutable raw data
│   ├── prices/
│   ├── fundamentals/
│   └── alternative/
├── processed/                    # Calculated features
│   ├── technical/
│   ├── fundamental/
│   └── alternative/
├── metadata/                     # Feature documentation
│   ├── feature_catalog.yaml     # All features with descriptions
│   ├── lineage/                 # How each feature is calculated
│   └── quality/                 # Data quality metrics
└── point_in_time/               # PIT snapshots for backtesting
    └── snapshots/               # Daily snapshots of feature values
```

---

### 3.3 Backtesting & Validation Framework

#### 3.3.1 Backtesting Engine Requirements

**Core Capabilities:**
- Event-driven simulation (not vectorized) for accuracy
- Support for multiple timeframes (tick, minute, daily)
- Realistic order execution modeling
- Transaction cost modeling (commission, slippage, market impact)
- Position sizing and portfolio construction
- Multi-asset, multi-strategy support

**Execution Realism:**
```python
class ExecutionModel:
    """
    Model realistic execution, not idealized fills.
    """
    
    def __init__(self):
        self.commission_per_share = 0.005  # $0.005/share
        self.min_commission = 1.0          # $1 minimum
        self.slippage_model = "sqrt_impact"
        
    def estimate_slippage(self, order_size, adv, volatility):
        """
        Market impact model (simplified Almgren-Chriss)
        
        Impact = σ * sqrt(Q / ADV) * constant
        
        Where:
        - σ = daily volatility
        - Q = order quantity
        - ADV = average daily volume
        """
        participation_rate = order_size / adv
        impact = volatility * np.sqrt(participation_rate) * 0.1
        return impact
    
    def fill_order(self, order, market_data):
        """
        Simulate order fill with realistic assumptions.
        """
        # Check liquidity constraints
        if order.quantity > market_data.volume * 0.1:
            # Can't be more than 10% of daily volume
            raise InsufficientLiquidityError()
        
        # Calculate execution price
        slippage = self.estimate_slippage(
            order.quantity,
            market_data.adv,
            market_data.volatility
        )
        
        if order.side == "BUY":
            exec_price = market_data.close * (1 + slippage)
        else:
            exec_price = market_data.close * (1 - slippage)
            
        return Fill(price=exec_price, quantity=order.quantity)
```

#### 3.3.2 Statistical Validation Methods

**Required Tests:**

| Test | Purpose | Implementation |
|------|---------|----------------|
| Walk-Forward Analysis | Out-of-sample validation | Rolling train/test windows |
| Combinatorial Purged CV | Avoid leakage in time series | Multiple non-overlapping test periods |
| Permutation Testing | Statistical significance | Shuffle returns, compare to actual |
| Bootstrap Analysis | Confidence intervals | Resample with replacement |
| Multiple Testing Correction | Avoid false discoveries | Bonferroni, FDR control |

**Walk-Forward Framework:**
```python
class WalkForwardValidator:
    """
    Implements rigorous walk-forward validation.
    """
    
    def __init__(
        self,
        train_period_days=504,      # 2 years training
        test_period_days=63,        # 3 months testing
        embargo_days=5,             # Gap to prevent leakage
        min_train_samples=252       # Minimum training data
    ):
        self.train_period = train_period_days
        self.test_period = test_period_days
        self.embargo = embargo_days
        
    def generate_splits(self, data):
        """
        Generate non-overlapping train/test splits.
        
        |--TRAIN--|embargo|--TEST--|
                         |--TRAIN--|embargo|--TEST--|
        """
        splits = []
        for fold in self.get_fold_boundaries(data):
            train_end = fold.train_end
            test_start = train_end + timedelta(days=self.embargo)
            test_end = test_start + timedelta(days=self.test_period)
            
            splits.append({
                'train': (fold.train_start, train_end),
                'test': (test_start, test_end)
            })
        return splits
```

**Permutation Testing:**
```python
def permutation_test(strategy_returns, benchmark_returns, n_permutations=10000):
    """
    Test if strategy outperformance is statistically significant.
    
    Null hypothesis: Strategy has no skill (excess returns due to chance)
    """
    observed_alpha = (strategy_returns - benchmark_returns).mean()
    
    null_distribution = []
    for _ in range(n_permutations):
        # Shuffle the pairing of strategy and benchmark returns
        shuffled = np.random.permutation(strategy_returns)
        null_alpha = (shuffled - benchmark_returns).mean()
        null_distribution.append(null_alpha)
    
    # p-value: probability of observing this alpha by chance
    p_value = np.mean(np.array(null_distribution) >= observed_alpha)
    
    return {
        'observed_alpha': observed_alpha,
        'p_value': p_value,
        'significant_at_5pct': p_value < 0.05,
        'null_distribution': null_distribution
    }
```

**Multiple Testing Correction:**
```python
def control_false_discovery_rate(p_values, alpha=0.05):
    """
    Benjamini-Hochberg procedure for FDR control.
    
    When testing many strategies, some will appear significant by chance.
    This controls the expected proportion of false discoveries.
    """
    n = len(p_values)
    sorted_indices = np.argsort(p_values)
    sorted_pvalues = p_values[sorted_indices]
    
    # BH threshold
    thresholds = (np.arange(1, n + 1) / n) * alpha
    
    # Find largest p-value below threshold
    below_threshold = sorted_pvalues <= thresholds
    if not below_threshold.any():
        return []  # No significant results
    
    max_significant = np.max(np.where(below_threshold)[0])
    significant_indices = sorted_indices[:max_significant + 1]
    
    return significant_indices
```

#### 3.3.3 Performance Metrics

**Required Metrics:**
```python
class PerformanceAnalyzer:
    """
    Comprehensive performance analysis.
    """
    
    def calculate_metrics(self, returns, benchmark_returns=None):
        return {
            # Return metrics
            'total_return': self.total_return(returns),
            'cagr': self.cagr(returns),
            'mtd': self.month_to_date(returns),
            'ytd': self.year_to_date(returns),
            
            # Risk metrics
            'volatility': self.annualized_volatility(returns),
            'downside_volatility': self.downside_deviation(returns),
            'max_drawdown': self.max_drawdown(returns),
            'avg_drawdown': self.average_drawdown(returns),
            'drawdown_duration': self.max_drawdown_duration(returns),
            'var_95': self.value_at_risk(returns, 0.95),
            'cvar_95': self.conditional_var(returns, 0.95),
            
            # Risk-adjusted metrics
            'sharpe_ratio': self.sharpe_ratio(returns),
            'sortino_ratio': self.sortino_ratio(returns),
            'calmar_ratio': self.calmar_ratio(returns),
            'omega_ratio': self.omega_ratio(returns),
            'information_ratio': self.information_ratio(returns, benchmark_returns),
            
            # Statistical metrics
            'skewness': self.skewness(returns),
            'kurtosis': self.kurtosis(returns),
            'hit_rate': self.win_rate(returns),
            'profit_factor': self.profit_factor(returns),
            'avg_win_loss_ratio': self.avg_win_loss_ratio(returns),
            
            # Benchmark-relative
            'alpha': self.jensen_alpha(returns, benchmark_returns),
            'beta': self.beta(returns, benchmark_returns),
            'correlation': self.correlation(returns, benchmark_returns),
            'tracking_error': self.tracking_error(returns, benchmark_returns),
            'capture_ratio_up': self.upside_capture(returns, benchmark_returns),
            'capture_ratio_down': self.downside_capture(returns, benchmark_returns),
        }
```

#### 3.3.4 Holdout Periods

**Multi-Level Holdout Structure:**
```
Full Data Timeline:
|-------|-----------------|----------|----------|
  Burn   Development       Validation  Final Test
  (warm-up) (train/test)   (paper trade) (NEVER TOUCH)

- Burn-in: Data for feature calculation warm-up (e.g., 252 days)
- Development: Walk-forward training and testing
- Validation: Paper trading simulation (3-6 months)
- Final Test: Absolute holdout, used ONCE before live trading
```

---

### 3.4 Strategy Research Framework

#### 3.4.1 Strategy Categories

**Supported Strategy Types:**
```
Strategy Taxonomy:
├── Momentum
│   ├── Time-series momentum (trend following)
│   ├── Cross-sectional momentum (relative strength)
│   └── Factor momentum
├── Mean Reversion
│   ├── Statistical arbitrage (pairs trading)
│   ├── Oversold/overbought
│   └── Event-driven mean reversion
├── Value
│   ├── Fundamental value
│   ├── Deep value
│   └── Quality-adjusted value
├── Carry
│   ├── Dividend capture
│   └── Options premium harvesting
├── Volatility
│   ├── Volatility arbitrage
│   ├── Dispersion trading
│   └── Vol risk premium
├── Sentiment
│   ├── News-driven
│   ├── Social sentiment
│   └── Contrarian sentiment
├── Event-Driven
│   ├── Earnings
│   ├── M&A/spinoffs
│   └── Index rebalancing
└── Machine Learning
    ├── Supervised (classification, regression)
    ├── Reinforcement learning
    └── Ensemble methods
```

#### 3.4.2 Strategy Definition Schema

```python
@dataclass
class StrategyDefinition:
    """
    Standardized strategy definition for documentation and execution.
    """
    # Identification
    strategy_id: str
    name: str
    version: str
    author: str  # Can be "agent" or human name
    created_date: datetime
    
    # Classification
    category: str  # From taxonomy above
    subcategory: str
    asset_classes: List[str]
    
    # Universe
    universe_definition: UniverseConfig
    
    # Signal Generation
    features_used: List[str]
    signal_logic: str  # Description or code reference
    signal_frequency: str  # daily, intraday, etc.
    
    # Portfolio Construction
    position_sizing_method: str
    max_position_size: float
    max_sector_exposure: float
    max_positions: int
    rebalance_frequency: str
    
    # Risk Management
    stop_loss: Optional[float]
    take_profit: Optional[float]
    max_drawdown_exit: float
    volatility_targeting: Optional[float]
    
    # Execution
    order_type: str
    execution_algo: str
    urgency: str
    
    # Hypothesis
    hypothesis: str  # Why this should work
    edge_source: str  # Where alpha comes from
    expected_decay: str  # How quickly edge might decay
    
    # Dependencies
    data_requirements: List[str]
    feature_dependencies: List[str]
    
    # Performance Targets
    target_sharpe: float
    target_max_drawdown: float
    target_cagr: float
```

#### 3.4.3 Model Types

**Heuristic/Rule-Based:**
```python
class MomentumStrategy(RuleBasedStrategy):
    """
    Example: 12-1 month momentum
    """
    def generate_signals(self, data):
        # Calculate 12-month return, skip most recent month
        momentum = data['close'].pct_change(252).shift(21)
        
        # Rank cross-sectionally
        ranks = momentum.rank(pct=True, axis=1)
        
        # Long top quintile, short bottom quintile
        signals = pd.DataFrame(0, index=ranks.index, columns=ranks.columns)
        signals[ranks > 0.8] = 1   # Long
        signals[ranks < 0.2] = -1  # Short
        
        return signals
```

**Machine Learning:**
```python
class MLStrategy(MachineLearningStrategy):
    """
    ML-based strategy with proper validation.
    """
    def __init__(self):
        self.model = None
        self.feature_importance = None
        
    def train(self, X_train, y_train):
        """
        Training with embedded cross-validation.
        """
        # Use purged k-fold to avoid leakage
        cv = PurgedKFold(n_splits=5, embargo_td=pd.Timedelta(days=5))
        
        # Model selection with hyperparameter tuning
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,  # Shallow to avoid overfitting
            min_samples_leaf=50,
            random_state=42
        )
        
        # Cross-validated training
        scores = cross_val_score(self.model, X_train, y_train, cv=cv)
        
        # Fit final model
        self.model.fit(X_train, y_train)
        self.feature_importance = self.model.feature_importances_
        
        return scores
    
    def predict(self, X):
        """
        Generate predictions (probabilities for risk management).
        """
        return self.model.predict_proba(X)[:, 1]
```

**Ensemble/Meta-Strategy:**
```python
class EnsembleStrategy(Strategy):
    """
    Combine multiple strategies with dynamic weighting.
    """
    def __init__(self, strategies, combination_method='risk_parity'):
        self.strategies = strategies
        self.combination_method = combination_method
        self.weights = None
        
    def calculate_weights(self, historical_returns):
        """
        Calculate strategy weights based on method.
        """
        if self.combination_method == 'risk_parity':
            # Inverse volatility weighting
            vols = historical_returns.std()
            self.weights = (1 / vols) / (1 / vols).sum()
            
        elif self.combination_method == 'mean_variance':
            # Markowitz optimization
            self.weights = self.optimize_mean_variance(historical_returns)
            
        elif self.combination_method == 'equal_weight':
            self.weights = np.ones(len(self.strategies)) / len(self.strategies)
            
        return self.weights
```

---

### 3.5 Alternative Data Integration

#### 3.5.1 Data Source Categories

**Structured Alternative Data:**
| Source | Data Type | Latency | Cost |
|--------|-----------|---------|------|
| SEC EDGAR | Filings, insider transactions | T+0 to T+1 | Free |
| Patent databases | Patent filings, grants | Weekly | Free/Low |
| Government data | Economic indicators, trade | Varies | Free |
| Earnings call transcripts | Text | T+0 | Free-Moderate |
| Analyst estimates | Consensus, revisions | T+0 | Moderate |

**Unstructured/Semi-Structured:**
| Source | Data Type | Processing Required | Potential Signal |
|--------|-----------|---------------------|------------------|
| News articles | Text | NLP, sentiment | Event detection, sentiment |
| Social media | Text | NLP, filtering | Retail sentiment, trending |
| Company blogs | Text | NLP | Product launches, strategy |
| Job postings | Text | NLP, aggregation | Growth signals |
| Web traffic | Numeric | Normalization | Business momentum |
| App rankings | Numeric | Normalization | Product adoption |

#### 3.5.2 Web Scraping Framework

```python
class WebScrapingPipeline:
    """
    Ethical, compliant web scraping for alternative data.
    """
    
    def __init__(self):
        self.rate_limiter = RateLimiter(requests_per_second=0.5)
        self.user_agent = "TradingResearchBot/1.0 (research@company.com)"
        
    def scrape_with_compliance(self, url):
        """
        Scrape with respect for robots.txt and rate limits.
        """
        # Check robots.txt
        if not self.is_allowed(url):
            raise PermissionError(f"Scraping not allowed: {url}")
        
        # Rate limit
        self.rate_limiter.wait()
        
        # Fetch with proper headers
        response = requests.get(url, headers={'User-Agent': self.user_agent})
        
        return response
    
    def extract_financial_signals(self, html):
        """
        Extract relevant signals from scraped content.
        """
        # Parse HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract based on source type
        # ... source-specific extraction logic
        
        return signals
```

#### 3.5.3 NLP Pipeline for Text Data

```python
class FinancialNLPPipeline:
    """
    NLP processing for financial text data.
    """
    
    def __init__(self):
        self.sentiment_model = self.load_financial_sentiment_model()
        self.embedding_model = self.load_embedding_model()
        self.entity_recognizer = self.load_financial_ner()
        
    def process_text(self, text, source_type):
        """
        Full NLP pipeline for financial text.
        """
        # Clean and normalize
        cleaned = self.clean_text(text)
        
        # Entity recognition (companies, people, products)
        entities = self.entity_recognizer.extract(cleaned)
        
        # Sentiment analysis
        sentiment = self.sentiment_model.predict(cleaned)
        
        # Generate embeddings for similarity/clustering
        embeddings = self.embedding_model.encode(cleaned)
        
        # Source-specific adjustments
        if source_type == 'social_media':
            # Social media often has inverse signal (contrarian)
            sentiment['contrarian_signal'] = -sentiment['raw_sentiment']
        
        return {
            'entities': entities,
            'sentiment': sentiment,
            'embeddings': embeddings,
            'processed_at': datetime.utcnow()
        }
    
    def aggregate_sentiment(self, texts, entity, time_window):
        """
        Aggregate sentiment for an entity over time.
        """
        relevant = [t for t in texts if entity in t['entities']]
        
        # Volume-weighted sentiment
        total_volume = len(relevant)
        weighted_sentiment = np.mean([t['sentiment']['score'] for t in relevant])
        
        # Sentiment momentum (change in sentiment)
        recent = [t for t in relevant if t['timestamp'] > time_window.start]
        older = [t for t in relevant if t['timestamp'] <= time_window.start]
        
        sentiment_momentum = (
            np.mean([t['sentiment']['score'] for t in recent]) -
            np.mean([t['sentiment']['score'] for t in older])
        )
        
        return {
            'entity': entity,
            'sentiment': weighted_sentiment,
            'sentiment_momentum': sentiment_momentum,
            'volume': total_volume,
            'confidence': self.calculate_confidence(total_volume)
        }
```

#### 3.5.4 Budget Picks Discovery

```python
class BudgetPicksResearcher:
    """
    Discover undervalued opportunities not visible from price data alone.
    
    Target: Small/mid-caps with positive alternative data signals
    but without corresponding price momentum yet.
    """
    
    def __init__(self):
        self.alternative_signals = ['sentiment', 'web_traffic', 'job_postings', 'patent_activity']
        
    def score_opportunity(self, symbol, data):
        """
        Score a potential budget pick.
        """
        scores = {}
        
        # Price hasn't moved (no momentum)
        price_momentum = data['returns_63d']
        scores['price_dormant'] = 1 if abs(price_momentum) < 0.1 else 0
        
        # But alternative signals are improving
        for signal in self.alternative_signals:
            signal_momentum = data[f'{signal}_momentum']
            scores[f'{signal}_improving'] = 1 if signal_momentum > 0.5 else 0
        
        # Low analyst coverage (less efficient)
        scores['under_covered'] = 1 if data['analyst_count'] < 5 else 0
        
        # Reasonable valuation
        scores['not_expensive'] = 1 if data['pe_percentile'] < 0.7 else 0
        
        # Composite score
        total_score = sum(scores.values()) / len(scores)
        
        return {
            'symbol': symbol,
            'composite_score': total_score,
            'component_scores': scores,
            'hypothesis': self.generate_hypothesis(scores)
        }
    
    def generate_hypothesis(self, scores):
        """
        Generate a hypothesis for why this might be a good pick.
        """
        improving_signals = [k for k, v in scores.items() if v > 0.5 and 'improving' in k]
        
        hypothesis = f"Stock is dormant in price but showing improvement in: {', '.join(improving_signals)}. "
        hypothesis += "This divergence may indicate undiscovered value."
        
        return hypothesis
```

---

### 3.6 Research Documentation System

#### 3.6.1 Research Knowledge Base Structure

```
research_kb/
├── experiments/
│   ├── EXP-2024-001/
│   │   ├── hypothesis.md
│   │   ├── methodology.md
│   │   ├── code/
│   │   ├── results/
│   │   │   ├── metrics.json
│   │   │   ├── visualizations/
│   │   │   └── statistical_tests.json
│   │   ├── conclusions.md
│   │   └── metadata.yaml
│   └── ...
├── strategies/
│   ├── active/
│   │   └── STRAT-MOM-001/
│   │       ├── definition.yaml
│   │       ├── backtest_results/
│   │       ├── live_performance/
│   │       └── modifications_log.md
│   ├── archived/
│   └── candidates/
├── features/
│   ├── catalog.yaml
│   ├── documentation/
│   └── performance/  # Predictive power of each feature
├── data_sources/
│   ├── inventory.yaml
│   ├── quality_reports/
│   └── integration_guides/
├── models/
│   ├── trained/
│   ├── versioning/
│   └── performance_tracking/
└── meta/
    ├── research_backlog.md
    ├── failed_hypotheses.md  # Important! Learn from failures
    └── agent_activity_log.md
```

#### 3.6.2 Experiment Documentation Standard

```yaml
# experiments/EXP-2024-042/metadata.yaml
experiment_id: EXP-2024-042
title: "Social Sentiment Contrarian Signal on Retail Favorites"
created_by: research_agent_v2
created_at: 2024-11-15T14:30:00Z
status: completed

hypothesis: |
  Extremely positive social media sentiment on retail-favorite stocks 
  (GME, AMC, TSLA, etc.) is a contrarian sell signal, as it often 
  precedes mean reversion.

methodology:
  universe: "retail_favorites"  # Custom universe
  features_tested:
    - social_sentiment_7d_ma
    - social_volume_zscore
    - sentiment_momentum_3d
  target: forward_5d_return
  test_type: walk_forward
  train_period: 504 days
  test_period: 63 days
  statistical_tests:
    - permutation_test
    - bootstrap_ci

results_summary:
  sharpe_ratio: 1.24
  p_value: 0.023
  significant: true
  edge_magnitude: "2.3% monthly excess return"

conclusions: |
  Hypothesis confirmed. Strong contrarian signal exists.
  However, signal strength has decayed over time (2.8% in 2021, 
  1.5% in 2023), suggesting crowding.

next_steps:
  - Test on broader universe
  - Combine with options flow data
  - Investigate regime dependency

related_experiments:
  - EXP-2024-038  # Options flow study
  - EXP-2024-029  # Sentiment baseline

tags:
  - sentiment
  - contrarian
  - retail_favorites
  - social_media
```

#### 3.6.3 Agent Research Interface

```python
class ResearchKnowledgeBase:
    """
    Interface for agents to interact with research documentation.
    """
    
    def query_experiments(
        self,
        filters: Dict = None,
        tags: List[str] = None,
        date_range: Tuple = None,
        min_sharpe: float = None
    ) -> List[Experiment]:
        """
        Search past experiments.
        """
        pass
    
    def get_failed_hypotheses(self, category: str) -> List[Experiment]:
        """
        Learn from what didn't work.
        """
        pass
    
    def get_feature_performance(self, feature_name: str) -> FeatureStats:
        """
        Get historical predictive power of a feature.
        """
        pass
    
    def suggest_next_experiments(self) -> List[ExperimentProposal]:
        """
        Based on past results, suggest promising research directions.
        """
        # Find high-performing areas with unexplored variations
        # Identify features that worked but weren't fully exploited
        # Suggest combinations that haven't been tried
        pass
    
    def document_experiment(self, experiment: Experiment):
        """
        Save experiment results with full audit trail.
        """
        pass
```

---

### 3.7 Live Simulation & Paper Trading

#### 3.7.1 Paper Trading Engine

```python
class PaperTradingEngine:
    """
    Simulate live trading with realistic conditions.
    """
    
    def __init__(self, initial_capital: float):
        self.capital = initial_capital
        self.positions = {}
        self.order_book = []
        self.trade_log = []
        self.performance_tracker = PerformanceTracker()
        
    def run_daily_simulation(self, date: datetime, strategies: List[Strategy]):
        """
        Run one day of paper trading simulation.
        """
        # 1. Get market data (delayed or EOD)
        market_data = self.data_provider.get_data(date)
        
        # 2. Update positions with current prices
        self.mark_to_market(market_data)
        
        # 3. Generate signals from strategies
        all_signals = []
        for strategy in strategies:
            signals = strategy.generate_signals(market_data)
            all_signals.append({
                'strategy': strategy.name,
                'signals': signals
            })
        
        # 4. Combine signals and construct target portfolio
        target_portfolio = self.portfolio_constructor.construct(
            signals=all_signals,
            current_positions=self.positions,
            capital=self.capital
        )
        
        # 5. Generate orders
        orders = self.generate_orders(target_portfolio)
        
        # 6. Simulate execution
        for order in orders:
            fill = self.execution_simulator.fill(order, market_data)
            self.process_fill(fill)
        
        # 7. Update performance metrics
        self.performance_tracker.update(date, self.get_portfolio_value())
        
        # 8. Log everything
        self.log_daily_activity(date, market_data, orders, target_portfolio)
        
        return self.get_daily_summary()
    
    def get_portfolio_value(self):
        """
        Calculate current portfolio value.
        """
        position_value = sum(
            pos.quantity * pos.current_price 
            for pos in self.positions.values()
        )
        return self.capital + position_value
```

#### 3.7.2 Real-Time Data Pipeline

```python
class RealTimeDataPipeline:
    """
    Ingest and process real-time market data.
    """
    
    def __init__(self):
        self.data_sources = []
        self.feature_calculator = RealTimeFeatureCalculator()
        self.signal_generator = RealTimeSignalGenerator()
        
    async def process_market_data(self, data_stream):
        """
        Process incoming market data stream.
        """
        async for tick in data_stream:
            # Update price database
            await self.update_prices(tick)
            
            # Recalculate affected features
            updated_features = await self.feature_calculator.update(tick)
            
            # Check for signal triggers
            if self.should_check_signals(tick):
                signals = await self.signal_generator.generate(updated_features)
                
                if signals:
                    await self.publish_signals(signals)
    
    def should_check_signals(self, tick):
        """
        Determine if we should generate signals.
        
        For daily strategies: Only at market close
        For intraday: Based on configured frequency
        """
        if self.strategy_frequency == 'daily':
            return tick.is_market_close
        elif self.strategy_frequency == '15min':
            return tick.timestamp.minute % 15 == 0
        else:
            return True  # Every tick
```

---

### 3.8 Execution Engine

#### 3.8.1 Order Management System

```python
class OrderManagementSystem:
    """
    Manage orders from generation to execution.
    """
    
    def __init__(self, broker_connection, risk_limits):
        self.broker = broker_connection
        self.risk_limits = risk_limits
        self.pending_orders = {}
        self.executed_orders = {}
        
    async def submit_order(self, order: Order) -> OrderResult:
        """
        Submit order with pre-trade risk checks.
        """
        # 1. Pre-trade risk checks
        risk_check = self.pre_trade_risk_check(order)
        if not risk_check.passed:
            return OrderResult(
                status='REJECTED',
                reason=risk_check.failure_reason
            )
        
        # 2. Apply execution algorithm
        if order.algo:
            sub_orders = self.apply_execution_algo(order)
        else:
            sub_orders = [order]
        
        # 3. Submit to broker
        results = []
        for sub_order in sub_orders:
            result = await self.broker.submit(sub_order)
            results.append(result)
            
            # Track in pending
            self.pending_orders[result.order_id] = sub_order
        
        return results
    
    def pre_trade_risk_check(self, order: Order) -> RiskCheckResult:
        """
        Comprehensive pre-trade risk validation.
        """
        checks = {
            'position_limit': self.check_position_limit(order),
            'sector_limit': self.check_sector_limit(order),
            'concentration': self.check_concentration(order),
            'daily_loss_limit': self.check_daily_loss_limit(order),
            'order_size': self.check_order_size(order),
            'price_deviation': self.check_price_deviation(order),
        }
        
        failed = [k for k, v in checks.items() if not v]
        
        return RiskCheckResult(
            passed=len(failed) == 0,
            failure_reason=failed
        )
```

#### 3.8.2 Risk Management System

```python
class RiskManagementSystem:
    """
    Real-time risk monitoring and control.
    """
    
    def __init__(self, config: RiskConfig):
        self.config = config
        self.alerts = AlertSystem()
        
    def configure_limits(self):
        """
        Define risk limits.
        """
        self.limits = {
            # Position limits
            'max_position_pct': 0.05,       # 5% max in single position
            'max_sector_pct': 0.25,         # 25% max in single sector
            'max_positions': 50,            # Max 50 positions
            
            # Loss limits
            'daily_loss_limit': 0.02,       # 2% max daily loss
            'weekly_loss_limit': 0.05,      # 5% max weekly loss
            'max_drawdown': 0.15,           # 15% max drawdown
            
            # Volatility limits
            'max_portfolio_vol': 0.20,      # 20% annualized vol target
            'var_95_limit': 0.03,           # 3% daily VaR limit
            
            # Liquidity limits
            'max_adv_pct': 0.10,            # 10% of ADV max
            'min_days_to_exit': 5,          # Must be able to exit in 5 days
        }
    
    def check_portfolio_risk(self, portfolio: Portfolio) -> RiskReport:
        """
        Comprehensive portfolio risk check.
        """
        report = RiskReport()
        
        # Position concentration
        for position in portfolio.positions:
            pct = position.value / portfolio.total_value
            if pct > self.limits['max_position_pct']:
                report.add_violation(f"Position {position.symbol} exceeds limit: {pct:.1%}")
        
        # Sector concentration
        sector_exposures = portfolio.get_sector_exposures()
        for sector, exposure in sector_exposures.items():
            if exposure > self.limits['max_sector_pct']:
                report.add_violation(f"Sector {sector} exceeds limit: {exposure:.1%}")
        
        # Portfolio volatility
        portfolio_vol = self.calculate_portfolio_vol(portfolio)
        if portfolio_vol > self.limits['max_portfolio_vol']:
            report.add_warning(f"Portfolio vol exceeds target: {portfolio_vol:.1%}")
        
        # Drawdown check
        current_dd = portfolio.current_drawdown
        if current_dd > self.limits['max_drawdown']:
            report.add_critical(f"Max drawdown breached: {current_dd:.1%}")
            self.trigger_emergency_delever()
        
        return report
    
    def trigger_emergency_delever(self):
        """
        Emergency position reduction when critical limits breached.
        """
        self.alerts.send_critical("EMERGENCY DELEVER TRIGGERED")
        
        # Reduce all positions by 50%
        for position in self.portfolio.positions:
            self.order_manager.submit_order(
                Order(
                    symbol=position.symbol,
                    side='SELL',
                    quantity=position.quantity * 0.5,
                    order_type='MARKET',
                    urgency='IMMEDIATE'
                )
            )
```

#### 3.8.3 Broker Integration

```python
class BrokerInterface:
    """
    Abstract interface for broker connections.
    Support multiple brokers for redundancy.
    """
    
    # Supported brokers:
    # - Interactive Brokers (recommended for automation)
    # - Alpaca (API-first, good for small accounts)
    # - TD Ameritrade / Schwab
    # - Tradier
    
    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult:
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        pass
    
    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        pass
    
    @abstractmethod
    async def subscribe_market_data(self, symbols: List[str]) -> AsyncIterator:
        pass


class InteractiveBrokersAdapter(BrokerInterface):
    """
    Interactive Brokers implementation using ib_insync.
    """
    
    def __init__(self, config: IBConfig):
        from ib_insync import IB
        self.ib = IB()
        self.config = config
        
    async def connect(self):
        await self.ib.connectAsync(
            host=self.config.host,
            port=self.config.port,
            clientId=self.config.client_id
        )
    
    async def submit_order(self, order: Order) -> OrderResult:
        from ib_insync import Stock, LimitOrder, MarketOrder
        
        contract = Stock(order.symbol, 'SMART', 'USD')
        
        if order.order_type == 'LIMIT':
            ib_order = LimitOrder(
                action='BUY' if order.side == 'BUY' else 'SELL',
                totalQuantity=order.quantity,
                lmtPrice=order.limit_price
            )
        else:
            ib_order = MarketOrder(
                action='BUY' if order.side == 'BUY' else 'SELL',
                totalQuantity=order.quantity
            )
        
        trade = self.ib.placeOrder(contract, ib_order)
        
        return OrderResult(
            order_id=trade.order.orderId,
            status='SUBMITTED'
        )
```

---

### 3.9 Agent Orchestration

#### 3.9.1 Agent Architecture

```
Agent Hierarchy:
├── Orchestrator Agent (Claude Code)
│   ├── Manages overall workflow
│   ├── Prioritizes research tasks
│   ├── Approves strategy deployments
│   └── Escalates to human when needed
├── Research Agent
│   ├── Generates hypotheses
│   ├── Designs experiments
│   ├── Analyzes results
│   └── Documents findings
├── Data Agent
│   ├── Manages data pipelines
│   ├── Monitors data quality
│   ├── Integrates new sources
│   └── Calculates features
├── Backtesting Agent
│   ├── Runs backtests
│   ├── Validates strategies
│   ├── Reports statistical significance
│   └── Flags potential issues
├── Execution Agent
│   ├── Generates orders
│   ├── Monitors fills
│   ├── Manages positions
│   └── Reports execution quality
└── Risk Agent
    ├── Monitors portfolio risk
    ├── Checks compliance
    ├── Triggers alerts
    └── Enforces limits
```

#### 3.9.2 Human Oversight Points

**Approval Required:**
| Action | Approval Level | Timeout |
|--------|---------------|---------|
| Deploy new strategy to paper trading | Email notification, auto-approve after 24h | 24h |
| Deploy strategy to live trading | Explicit approval required | None |
| Increase position limits | Explicit approval required | None |
| Emergency delever | Auto-execute, immediate notification | 0 |
| Add new data source | Auto-approve if free/legal | 24h |
| Modify risk limits | Explicit approval required | None |

**Daily Reports to Human:**
- Portfolio performance summary
- Active strategies performance
- Risk metrics and limit utilization
- Research progress and findings
- Anomaly alerts

#### 3.9.3 Agent Communication Protocol

```python
class AgentMessage:
    """
    Standardized message format for agent communication.
    """
    message_id: str
    timestamp: datetime
    sender: str
    recipient: str
    message_type: str  # 'request', 'response', 'alert', 'report'
    priority: str  # 'low', 'medium', 'high', 'critical'
    payload: Dict
    requires_response: bool
    timeout_seconds: Optional[int]


class OrchestratorAgent:
    """
    Main orchestrator that coordinates all agents.
    """
    
    async def run_daily_workflow(self):
        """
        Execute daily automated workflow.
        """
        # 1. Morning data check
        await self.data_agent.verify_data_quality()
        
        # 2. Update features
        await self.data_agent.calculate_daily_features()
        
        # 3. Generate signals for live strategies
        signals = await self.execution_agent.generate_signals()
        
        # 4. Risk check before trading
        risk_report = await self.risk_agent.pre_trade_check()
        
        if risk_report.has_critical:
            await self.alert_human(risk_report)
            return
        
        # 5. Execute trades (if market hours)
        if self.is_market_open():
            await self.execution_agent.execute_trades(signals)
        
        # 6. Run paper trading simulation
        await self.execution_agent.run_paper_trading()
        
        # 7. Research time (off-market hours)
        if not self.is_market_open():
            await self.research_agent.run_experiment()
        
        # 8. End of day reporting
        await self.generate_daily_report()
```

---

### 3.10 Infrastructure Requirements

#### 3.10.1 Compute Requirements

| Component | Specification | Notes |
|-----------|--------------|-------|
| Feature Calculation | 8+ CPU cores, 32GB RAM | Parallelized calculations |
| Backtesting | 16+ CPU cores, 64GB RAM | Walk-forward is expensive |
| ML Training | GPU recommended (RTX 3090+) | For deep learning models |
| Live Trading | 4 CPU cores, 16GB RAM | Low latency priority |
| Data Storage | 2TB+ SSD | Historical data |

#### 3.10.2 Data Storage

```
Storage Architecture:
├── Time-Series Database (TimescaleDB/InfluxDB)
│   └── Price data, features, signals
├── Document Database (MongoDB)
│   └── Research docs, unstructured data
├── Vector Database (Pinecone/Weaviate)
│   └── Text embeddings for similarity search
├── Relational Database (PostgreSQL)
│   └── Orders, trades, positions, metadata
└── Object Storage (S3/MinIO)
    └── Large files, model artifacts, backups
```

#### 3.10.3 External Services

**Required:**
- Market data provider (Polygon, Alpha Vantage, IEX Cloud, Yahoo Finance)
- Broker API (Interactive Brokers, Alpaca)
- News/sentiment data (Benzinga, News API, social scrapers)

**Recommended:**
- Fundamental data (Quandl/Nasdaq Data Link, Intrinio)
- Alternative data (Thinknum, Quiver Quantitative)
- Cloud compute for scaling (AWS/GCP/Azure)

---

## 4. Implementation Phases

### Phase 1: Foundation (Weeks 1-4)
- [ ] Set up development environment
- [ ] Implement data ingestion for prices (free sources)
- [ ] Build basic feature engineering pipeline
- [ ] Create simple backtesting engine
- [ ] Establish research documentation structure

### Phase 2: Core Trading (Weeks 5-8)
- [ ] Implement statistical validation framework
- [ ] Build portfolio construction module
- [ ] Add fundamental data integration
- [ ] Develop 3-5 baseline strategies
- [ ] Create performance reporting

### Phase 3: Alternative Data (Weeks 9-12)
- [ ] Integrate news sentiment
- [ ] Build web scraping infrastructure
- [ ] Implement NLP pipeline
- [ ] Develop budget picks discovery
- [ ] Test alternative signals

### Phase 4: Automation (Weeks 13-16)
- [ ] Design agent architecture
- [ ] Implement orchestrator agent
- [ ] Build research agent workflow
- [ ] Create human oversight interface
- [ ] Set up alerting system

### Phase 5: Live Trading (Weeks 17-20)
- [ ] Integrate broker API
- [ ] Build order management system
- [ ] Implement risk management
- [ ] Deploy paper trading
- [ ] Extensive testing

### Phase 6: Production (Weeks 21-24)
- [ ] Go-live with small capital
- [ ] Monitor and iterate
- [ ] Scale successful strategies
- [ ] Continuous research automation

---

## 5. Success Metrics

### Research Metrics
- Number of hypotheses tested per week
- Percentage of strategies passing statistical validation
- Time from hypothesis to backtest completion
- Documentation completeness score

### Trading Metrics
- Sharpe ratio (target: > 1.5)
- Maximum drawdown (limit: < 15%)
- Win rate (target: > 55%)
- Execution slippage vs. backtest

### Operational Metrics
- System uptime (target: 99.9%)
- Data quality score (target: > 99%)
- Alert response time (target: < 5 min)
- Human intervention frequency (target: < 1/day)

---

## 6. Risk Considerations

### Technical Risks
- Data feed failures → Implement redundant sources
- Broker API issues → Have backup broker
- Model degradation → Continuous monitoring and retraining

### Market Risks
- Black swan events → Position limits and stop losses
- Regime changes → Regime detection and adaptive strategies
- Crowding → Decay monitoring and alpha diversification

### Operational Risks
- Agent errors → Human oversight checkpoints
- Over-optimization → Strict validation protocols
- Execution drift → Regular reconciliation

---

## 7. Open Questions for Discussion

1. **Capital allocation**: What starting capital are you considering? This affects strategy selection (some strategies require scale).

2. **Trading frequency**: Daily rebalancing? Intraday? This affects infrastructure requirements significantly.

3. **Asset classes**: Start with equities only, or include options/futures from the beginning?

4. **Broker preference**: Do you have an existing brokerage relationship?

5. **Risk tolerance**: What maximum drawdown are you comfortable with?

6. **Automation level**: How much human oversight do you want for trading decisions?

7. **Alternative data budget**: Are you willing to pay for alternative data, or strictly free sources?

8. **Compliance requirements**: Any regulatory considerations (PDT rule, professional trader status)?

---

## 8. Next Steps

1. Review this document and provide feedback
2. Answer open questions above
3. Prioritize features for MVP
4. Set up development environment
5. Begin Phase 1 implementation

---

*Document Version: 1.0*
*Created: Research Planning Session*
*Status: Draft for Review*
