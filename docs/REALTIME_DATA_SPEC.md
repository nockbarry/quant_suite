# Real-Time Trading Data Infrastructure Specification

**Purpose**: Enhance intraday trading decisions with real-time news, technical analysis, options analytics, and automated alerts.

**Priority**: High - These gaps were identified during live trading on 2026-01-06.

---

## Table of Contents

1. [Live News Daemon](#1-live-news-daemon)
2. [Intraday Technical Analytics](#2-intraday-technical-analytics)
3. [Options Analytics Engine](#3-options-analytics-engine)
4. [Morning Open Protocol](#4-morning-open-protocol)
5. [Alert System](#5-alert-system)
6. [Sector & Market Breadth](#6-sector--market-breadth)
7. [Sentiment Indicators](#7-sentiment-indicators)
8. [Economic & Earnings Calendar](#8-economic--earnings-calendar)
9. [Position Risk Monitor](#9-position-risk-monitor)
10. [Implementation Priority](#10-implementation-priority)

---

## 1. Live News Daemon

### Problem
Pre-market research was excellent, but no news updates during the trading session. Missed the Fortune "Venezuela reality check" article mid-day that could have prompted earlier defensive action.

### Specification

```
Location: src/data/sources/realtime/news_daemon.py
Output: ~/quant_results/live_news/YYYY-MM-DD/
Update Frequency: Every 30 minutes during market hours (9:30am - 4:00pm ET)
```

### Data Sources (Free/Low-Cost)

| Source | Method | Rate Limit | Content |
|--------|--------|------------|---------|
| Yahoo Finance RSS | RSS feed | Unlimited | General market news |
| Google News API | REST API | 100/day free | Search by symbol |
| Finviz News | Web scrape | Respectful | Symbol-specific news |
| Reddit (r/wallstreetbets, r/stocks) | PRAW API | 60/min | Sentiment, trending |
| SEC EDGAR | REST API | 10/sec | 8-K filings, insider trades |
| Twitter/X | API v2 | 500k/month free | Breaking news, sentiment |
| Seeking Alpha | RSS | Unlimited | Analysis, opinions |
| Benzinga | RSS | Unlimited | Market news |

### Output Schema

```python
@dataclass
class NewsItem:
    timestamp: datetime
    source: str
    headline: str
    summary: str
    symbols: List[str]          # Mentioned tickers
    sentiment: float            # -1 to 1 (if analyzable)
    priority: str               # "BREAKING" | "HIGH" | "NORMAL" | "LOW"
    url: str
    relevance_score: float      # How relevant to our positions (0-1)

@dataclass
class NewsSummary:
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    items: List[NewsItem]
    portfolio_relevant: List[NewsItem]  # Filtered to our positions
    sentiment_shift: float              # Change in overall sentiment
    key_themes: List[str]               # ["Venezuela", "Fed", "Energy"]
```

### File Output

```
~/quant_results/live_news/2026-01-06/
├── news_0930.json      # First check at open
├── news_1000.json
├── news_1030.json
├── ...
├── news_1600.json      # Final check at close
├── daily_summary.json  # End of day compilation
└── alerts.json         # High-priority items only
```

### API Interface

```python
# src/data/sources/realtime/news_daemon.py

class NewsDaemon:
    def __init__(self, watchlist: List[str], output_dir: Path):
        """
        watchlist: Symbols to monitor (e.g., ['SLB', 'HAL', 'XLE'])
        """

    async def check_news(self) -> NewsSummary:
        """Run a single news check cycle."""

    async def start(self, interval_minutes: int = 30):
        """Start continuous monitoring."""

    async def stop(self):
        """Stop monitoring."""

    def get_latest(self) -> NewsSummary:
        """Get most recent news summary."""

    def get_portfolio_alerts(self) -> List[NewsItem]:
        """Get high-priority items for current positions."""

    def search(self, query: str, hours_back: int = 24) -> List[NewsItem]:
        """Search historical news."""
```

### LLM Integration

```python
def summarize_for_trading(news_items: List[NewsItem]) -> str:
    """
    Use Claude to create actionable trading summary:
    - What's the main narrative?
    - How does this affect our positions?
    - Any immediate action needed?
    """
```

---

## 2. Intraday Technical Analytics

### Problem
Only had price snapshots, not technical context. Couldn't see volume, VWAP, trend structure, or support/resistance tests.

### Specification

```
Location: src/data/pipeline/intraday_technicals.py
Data Source: yfinance (free) or Alpaca (if subscribed)
Candle Intervals: 1m, 5m, 15m
```

### Output Schema

```python
@dataclass
class IntradayTechnicals:
    symbol: str
    timestamp: datetime

    # Price Data
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    change_pct: float

    # Volume Analysis
    volume: int
    avg_volume_20d: int
    volume_ratio: float              # current / average
    cumulative_volume: int
    volume_profile: Dict[float, int] # price level -> volume

    # VWAP
    vwap: float
    price_vs_vwap: float             # distance from VWAP
    vwap_position: str               # "above" | "below" | "at"

    # Trend Analysis
    trend_1h: str                    # "uptrend" | "downtrend" | "ranging"
    trend_4h: str
    higher_highs: bool
    lower_lows: bool
    trend_strength: float            # 0-1

    # Support/Resistance
    support_levels: List[float]
    resistance_levels: List[float]
    nearest_support: float
    nearest_resistance: float
    support_distance: float          # $ away from nearest support
    support_tests_today: int         # How many times tested

    # Candlestick Patterns (last 5 candles)
    patterns: List[str]              # ["doji", "hammer", "engulfing"]
    reversal_signal: bool
    continuation_signal: bool

    # Moving Averages (intraday)
    ema_9: float
    ema_21: float
    sma_50: float                    # 50-period on 5m chart
    ma_alignment: str                # "bullish" | "bearish" | "mixed"

    # Momentum
    rsi_14: float
    macd: float
    macd_signal: float
    macd_histogram: float
    momentum_bias: str               # "bullish" | "bearish" | "neutral"

    # Range Analysis
    atr_14: float
    todays_range: float
    range_pct_of_atr: float          # How much of typical range used

    # Key Levels
    pivot: float
    r1: float
    r2: float
    s1: float
    s2: float

    # Summary
    bias: str                        # "bullish" | "bearish" | "neutral"
    strength: str                    # "strong" | "moderate" | "weak"
    action_signal: str               # "buy" | "sell" | "hold" | "watch"
    notes: List[str]                 # Human-readable observations

@dataclass
class MultiTimeframeTechnicals:
    symbol: str
    tf_1m: IntradayTechnicals
    tf_5m: IntradayTechnicals
    tf_15m: IntradayTechnicals
    alignment: str                   # "aligned_bullish" | "aligned_bearish" | "mixed"
```

### API Interface

```python
# src/data/pipeline/intraday_technicals.py

class IntradayTechnicalAnalyzer:
    def __init__(self, symbols: List[str]):
        """Initialize with watchlist."""

    def get_technicals(self, symbol: str, timeframe: str = "5m") -> IntradayTechnicals:
        """Get current technical state for symbol."""

    def get_multi_timeframe(self, symbol: str) -> MultiTimeframeTechnicals:
        """Get aligned analysis across timeframes."""

    def get_all(self) -> Dict[str, IntradayTechnicals]:
        """Get technicals for all watched symbols."""

    def detect_patterns(self, symbol: str) -> List[str]:
        """Detect candlestick patterns."""

    def find_levels(self, symbol: str) -> Dict[str, List[float]]:
        """Find support/resistance levels."""

    def get_summary(self, symbol: str) -> str:
        """Human-readable technical summary for LLM consumption."""
```

### Summary Output Format (for LLM)

```
SLB Technical Summary (2:30 PM ET):
  Price: $43.60 | VWAP: $43.85 (below, bearish)
  Volume: 1.2x average (elevated selling)
  Trend: Downtrend on 1h, tested $43.40 support twice
  Pattern: Lower highs since 10am, no reversal signals
  RSI: 38 (approaching oversold)
  Bias: BEARISH | Action: Watch $43.35 support closely

  Key Levels:
    Support: $43.35 (tested 2x), $42.80
    Resistance: $44.00, $44.50 (VWAP)
```

---

## 3. Options Analytics Engine

### Problem
Flying blind on options positions. Didn't know theta decay rate, delta exposure, or whether IV was elevated.

### Specification

```
Location: src/data/pipeline/options_analytics.py
Data Source: Yahoo Finance (free) or CBOE/IVolatility (paid)
```

### Output Schema

```python
@dataclass
class OptionGreeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float

@dataclass
class OptionAnalytics:
    symbol: str                      # Full option symbol
    underlying: str                  # e.g., "SLB"
    underlying_price: float
    strike: float
    expiration: date
    option_type: str                 # "call" | "put"
    days_to_expiry: int

    # Pricing
    bid: float
    ask: float
    mid: float
    last: float
    spread_pct: float                # (ask-bid)/mid

    # Greeks
    greeks: OptionGreeks

    # Dollar Greeks (per contract)
    dollar_delta: float              # delta * 100 * underlying_price
    dollar_theta: float              # theta * 100 (daily decay in $)
    dollar_gamma: float

    # Implied Volatility
    iv: float
    iv_rank: float                   # 0-100 percentile vs 52-week
    iv_percentile: float
    historical_vol_20d: float
    iv_vs_hv: float                  # IV premium/discount

    # Probability Analysis
    prob_itm: float                  # Probability of finishing ITM
    prob_profit: float               # Probability of profit at current price
    prob_50_pct_profit: float        # Probability of 50%+ gain
    expected_move: float             # 1 std dev move by expiry

    # Breakeven Analysis
    breakeven: float
    distance_to_breakeven: float
    distance_to_breakeven_pct: float

    # Time Decay Analysis
    theta_per_day: float             # $ lost per day per contract
    theta_acceleration: float        # Rate of theta increase
    optimal_exit_dte: int            # When theta accelerates (typically 21 DTE)

    # Volume & Open Interest
    volume: int
    open_interest: int
    volume_oi_ratio: float           # Unusual activity indicator

    # Recommendation
    hold_score: float                # 0-100, higher = better to hold
    roll_recommendation: bool        # Should consider rolling?
    suggested_action: str            # "hold" | "close" | "roll" | "add"
    notes: List[str]

@dataclass
class PositionOptionsAnalytics:
    """Portfolio-level options analysis"""
    total_delta: float               # Net delta exposure
    total_theta: float               # Daily theta decay (all positions)
    total_vega: float                # IV sensitivity
    max_loss: float                  # If all options expire worthless
    weighted_avg_iv: float
    positions: List[OptionAnalytics]
```

### API Interface

```python
# src/data/pipeline/options_analytics.py

class OptionsAnalyzer:
    def __init__(self):
        pass

    def analyze_option(self, symbol: str) -> OptionAnalytics:
        """Full analysis of single option position."""

    def analyze_portfolio(self, positions: List[str]) -> PositionOptionsAnalytics:
        """Analyze all options positions."""

    def get_greeks(self, symbol: str) -> OptionGreeks:
        """Quick Greeks lookup."""

    def get_iv_rank(self, underlying: str) -> float:
        """Get current IV rank for underlying."""

    def find_rolls(self, symbol: str) -> List[Dict]:
        """Find optimal roll candidates."""

    def get_summary(self, symbol: str) -> str:
        """Human-readable summary for LLM."""
```

### Summary Output Format (for LLM)

```
SLB Feb 6 $44 Call Analysis:
  Price: $1.46 | Underlying: $43.60
  Status: OTM by $0.40 (0.9%)

  Greeks:
    Delta: 0.42 | Theta: -$0.08/day | Vega: 0.12
    Dollar Theta: -$8/day per contract (5 contracts = -$40/day)

  IV Analysis:
    IV: 38% | IV Rank: 65 (elevated)
    HV20: 32% | IV Premium: +6%
    Note: IV elevated from Venezuela news - options expensive

  Probability:
    Prob ITM: 38% | Breakeven: $45.46
    Expected Move by Expiry: +/- $2.80

  Time Decay:
    31 DTE | Theta accelerates in 10 days
    Projected value in 1 week (flat): $1.10 (-25%)

  Recommendation: HOLD for earnings (Jan 23)
    Risk: Losing ~$40/day in theta
    Catalyst needed: Earnings beat + Venezuela progress
```

---

## 4. Morning Open Protocol

### Problem
By the time we "locked in" our plan at 10am, the Venezuela gap had already faded significantly. Needed faster assessment at open.

### Specification

```
Location: src/decision/morning_open.py
Trigger: Automatically runs at 9:35 AM ET
```

### Process Flow

```
9:30 AM - Market Opens
    │
9:35 AM - Open Assessment
    │
    ├── Compare pre-market prices to 9:35 prices
    │     - Which gaps are holding?
    │     - Which gaps are fading?
    │     - Volume confirmation?
    │
    ├── Sector scan
    │     - Is our sector leading or lagging?
    │     - Rotation signals?
    │
    ├── Position check
    │     - Any positions hit stops?
    │     - Any at critical levels?
    │
    └── Generate OPEN ASSESSMENT report
          - HOLD plan as-is
          - MODIFY plan (specify changes)
          - GO DEFENSIVE (reduce exposure)

9:45 AM - Second check (confirm or adjust)
```

### Output Schema

```python
@dataclass
class PreMarketVsOpen:
    symbol: str
    premarket_price: float
    premarket_change_pct: float
    open_price: float
    price_at_935: float
    gap_status: str              # "holding" | "fading" | "reversing" | "extending"
    gap_fade_pct: float          # How much of gap has faded
    volume_vs_avg: float
    assessment: str

@dataclass
class OpenAssessment:
    timestamp: datetime
    market_status: str           # "risk_on" | "risk_off" | "mixed"

    # Gap Analysis
    gaps: List[PreMarketVsOpen]
    gaps_holding: List[str]
    gaps_fading: List[str]

    # Sector Analysis
    sector_leader: str
    sector_laggard: str
    our_sector_rank: int         # 1 = leading, 11 = lagging
    rotation_signal: str         # "into_our_sector" | "out_of_our_sector" | "neutral"

    # Position Alerts
    stops_hit: List[str]
    near_support: List[str]
    near_resistance: List[str]

    # Recommendation
    plan_status: str             # "PROCEED" | "MODIFY" | "DEFENSIVE"
    modifications: List[str]     # Specific changes to morning plan
    priority_actions: List[str]  # Immediate actions needed

    # Confidence
    confidence: float            # 0-1 in the day's plan
    notes: str
```

### API Interface

```python
# src/decision/morning_open.py

class MorningOpenProtocol:
    def __init__(self, premarket_data: Dict, morning_plan: Dict):
        """
        premarket_data: Pre-market prices and research
        morning_plan: The trading plan from /trade-decision
        """

    async def run_assessment(self) -> OpenAssessment:
        """Run the 9:35 AM assessment."""

    def compare_gaps(self) -> List[PreMarketVsOpen]:
        """Compare pre-market to current prices."""

    def scan_sectors(self) -> Dict:
        """Quick sector rotation scan."""

    def check_positions(self) -> Dict:
        """Check all positions vs stops/levels."""

    def get_recommendation(self) -> str:
        """Get action recommendation."""
```

### Output Format (for LLM)

```
OPEN ASSESSMENT - 9:35 AM ET
════════════════════════════════════════

MARKET STATUS: RISK_OFF (energy fading, defensives leading)

GAP ANALYSIS:
  SLB: Pre-mkt +8.96% → 9:35 +2.1% → GAP FADING (77% faded)
  HAL: Pre-mkt +7.84% → 9:35 +0.5% → GAP FADING (94% faded)
  BKR: Pre-mkt +4.10% → 9:35 +1.2% → GAP FADING (71% faded)

  ⚠️ Venezuela rally fading fast on high volume

SECTOR RANK: Energy #9 of 11 (lagging)
ROTATION: Money flowing OUT of energy → Healthcare, Tech

POSITION ALERTS:
  - HAL approaching $31 support
  - No stops hit yet

RECOMMENDATION: GO DEFENSIVE
  1. Tighten stops on energy positions
  2. Consider closing weakest options (HAL calls)
  3. Reduce position sizes on any bounce

CONFIDENCE IN MORNING PLAN: 35% (down from 70%)
  Reason: Gap fade indicates market skepticism on Venezuela timeline
```

---

## 5. Alert System

### Problem
Manual monitoring every 2 minutes is inefficient and easy to miss critical levels.

### Specification

```
Location: src/alerts/alert_manager.py
Delivery: File-based + optional webhook (Discord/Slack/SMS)
```

### Alert Types

```python
@dataclass
class Alert:
    timestamp: datetime
    type: str                    # See types below
    priority: str                # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    symbol: str
    message: str
    current_value: float
    threshold: float
    action_suggested: str
    acknowledged: bool = False

# Alert Types
ALERT_TYPES = {
    # Price Alerts
    "PRICE_ABOVE": "Price crossed above threshold",
    "PRICE_BELOW": "Price crossed below threshold",
    "STOP_HIT": "Stop loss level breached",
    "SUPPORT_TEST": "Testing support level",
    "SUPPORT_BREAK": "Support level broken",
    "RESISTANCE_TEST": "Testing resistance level",
    "RESISTANCE_BREAK": "Resistance level broken",

    # Volume Alerts
    "VOLUME_SPIKE": "Unusual volume detected",
    "VOLUME_DRY_UP": "Volume significantly below average",

    # Options Alerts
    "THETA_WARNING": "Significant theta decay today",
    "IV_SPIKE": "IV increased significantly",
    "IV_CRUSH": "IV dropping (post-event)",
    "EXPIRY_WARNING": "Options expiring soon",

    # News Alerts
    "NEWS_BREAKING": "Breaking news on position",
    "NEWS_SENTIMENT_SHIFT": "Sentiment changed significantly",
    "SEC_FILING": "New SEC filing detected",

    # Portfolio Alerts
    "CONCENTRATION_HIGH": "Position concentration too high",
    "CORRELATION_SPIKE": "Positions becoming correlated",
    "DRAWDOWN_WARNING": "Daily loss exceeding threshold",
    "PDT_WARNING": "Approaching PDT limit",

    # Technical Alerts
    "TREND_CHANGE": "Trend reversal detected",
    "PATTERN_DETECTED": "Candlestick pattern formed",
    "DIVERGENCE": "Price/indicator divergence",
    "OVERSOLD": "RSI oversold",
    "OVERBOUGHT": "RSI overbought",
}
```

### Configuration

```yaml
# config/alerts.yaml

alerts:
  # Price alerts
  price_alerts:
    SLB:
      support: 43.35
      resistance: 45.00
      stop: 42.50
    HAL:
      support: 30.00
      stop: 29.50

  # Volume alerts
  volume:
    spike_threshold: 2.0        # 2x average
    dry_up_threshold: 0.3       # 30% of average

  # Options alerts
  options:
    theta_warning_pct: 5        # Alert if losing >5% to theta today
    expiry_warning_dte: 7       # Alert when <7 DTE
    iv_change_threshold: 20     # Alert on 20%+ IV change

  # Portfolio alerts
  portfolio:
    max_position_pct: 25
    max_sector_pct: 50
    max_daily_loss_pct: 5
    pdt_warning_threshold: 2    # Alert when 2 day trades remaining

  # Delivery
  delivery:
    file: true
    discord_webhook: null       # Optional
    slack_webhook: null         # Optional
    email: null                 # Optional
```

### API Interface

```python
# src/alerts/alert_manager.py

class AlertManager:
    def __init__(self, config_path: str):
        """Load alert configuration."""

    def add_price_alert(self, symbol: str, level: float, direction: str, priority: str):
        """Add a price alert."""

    def add_stop_alert(self, symbol: str, stop_price: float):
        """Add stop loss alert."""

    def check_all(self) -> List[Alert]:
        """Check all configured alerts."""

    def get_active_alerts(self) -> List[Alert]:
        """Get currently triggered alerts."""

    def acknowledge(self, alert_id: str):
        """Mark alert as acknowledged."""

    async def start_monitoring(self, interval_seconds: int = 60):
        """Start continuous alert monitoring."""

    async def stop_monitoring(self):
        """Stop monitoring."""
```

### Output Format

```
ALERTS - 2:30 PM ET
════════════════════════════════════════

🚨 CRITICAL:
  [14:28] STOP_HIT: VLO at $178.13 (stop: $179.00)
          Action: Execute stop loss sell

⚠️ HIGH:
  [14:15] SUPPORT_TEST: SLB testing $43.40 (support: $43.35)
          Action: Watch closely, prepare trim order

  [14:22] THETA_WARNING: SLB calls losing $40/day (5.5% of position)
          Action: Evaluate hold vs close

ℹ️ MEDIUM:
  [13:45] VOLUME_SPIKE: HAL volume 1.8x average (selling)
          Action: Monitor for breakdown
```

---

## 6. Sector & Market Breadth

### Problem
Didn't have real-time view of money flow between sectors. Couldn't quickly see that energy was lagging while broader market was up.

### Specification

```
Location: src/data/pipeline/market_breadth.py
Update Frequency: Every 5 minutes during market hours
```

### Output Schema

```python
@dataclass
class SectorData:
    symbol: str                  # XLE, XLF, XLK, etc.
    name: str                    # Energy, Financials, Technology
    price: float
    change_pct: float
    volume_ratio: float
    relative_strength: float     # vs SPY
    rank: int                    # 1 = leading, 11 = lagging
    flow_direction: str          # "inflow" | "outflow" | "neutral"

@dataclass
class MarketBreadth:
    timestamp: datetime

    # Index Data
    spy_price: float
    spy_change_pct: float
    qqq_price: float
    qqq_change_pct: float
    iwm_price: float
    iwm_change_pct: float

    # Breadth Indicators
    advancers: int
    decliners: int
    unchanged: int
    advance_decline_ratio: float
    advance_decline_line: float  # Cumulative
    new_highs: int
    new_lows: int
    high_low_ratio: float

    # Sector Rotation
    sectors: List[SectorData]
    leading_sectors: List[str]
    lagging_sectors: List[str]
    rotation_theme: str          # "risk_on" | "risk_off" | "defensive" | "cyclical"

    # VIX Structure
    vix: float
    vix_change_pct: float
    vix_term_structure: str      # "contango" | "backwardation"
    fear_level: str              # "complacent" | "cautious" | "fearful" | "panic"

    # Market Regime
    regime: str                  # "trending_up" | "trending_down" | "ranging" | "volatile"

    # Summary
    bias: str                    # "bullish" | "bearish" | "neutral"
    strength: str
    notes: List[str]
```

### API Interface

```python
# src/data/pipeline/market_breadth.py

class MarketBreadthAnalyzer:
    def __init__(self):
        pass

    def get_breadth(self) -> MarketBreadth:
        """Get current market breadth snapshot."""

    def get_sector_rotation(self) -> List[SectorData]:
        """Get sector rotation data."""

    def get_vix_analysis(self) -> Dict:
        """Analyze VIX and term structure."""

    def get_regime(self) -> str:
        """Determine current market regime."""

    def get_summary(self) -> str:
        """Human-readable summary for LLM."""
```

### Output Format (for LLM)

```
MARKET BREADTH - 2:30 PM ET
════════════════════════════════════════

INDICES:
  SPY: $691.62 (+0.57%)
  QQQ: $421.30 (+0.89%)
  IWM: $227.45 (+0.23%)

BREADTH: Bullish
  Advancers: 324 | Decliners: 176 | A/D: 1.84
  New Highs: 89 | New Lows: 12 | H/L: 7.4

SECTOR ROTATION:
  1. Healthcare  +1.62% ████████████████ LEADING
  2. Technology  +1.14% ███████████
  3. Financials  +0.28% ███
  ...
  10. Materials  -0.89% ░░░░░░░░░
  11. Energy     -2.21% ░░░░░░░░░░░░░░░░░░░░░░ LAGGING

  Theme: DEFENSIVE (money rotating out of cyclicals)
  ⚠️ Our sector (Energy) is the worst performer today

VIX: $14.80 (-0.67%)
  Structure: Contango (normal)
  Fear Level: Complacent

REGIME: Trending Up (narrow leadership)
```

---

## 7. Sentiment Indicators

### Problem
Didn't have view into positioning and sentiment that could signal extremes or reversals.

### Specification

```
Location: src/data/pipeline/sentiment.py
Update Frequency: Hourly during market hours
```

### Data Sources

| Indicator | Source | Update Freq |
|-----------|--------|-------------|
| Put/Call Ratio | CBOE | Real-time |
| VIX Term Structure | CBOE | Real-time |
| AAII Sentiment | AAII | Weekly |
| Fear & Greed Index | CNN | Daily |
| Options Flow | Unusual Whales / Manual | Real-time |
| Short Interest | FINRA | Bi-weekly |
| Insider Trading | SEC Form 4 | Daily |
| Social Sentiment | Reddit/Twitter | Real-time |

### Output Schema

```python
@dataclass
class SentimentIndicators:
    timestamp: datetime

    # Options Sentiment
    put_call_ratio: float
    put_call_5d_avg: float
    put_call_signal: str         # "bullish" | "bearish" | "neutral"
    equity_put_call: float
    index_put_call: float

    # VIX Analysis
    vix_spot: float
    vix_1m: float
    vix_3m: float
    vix_term_structure: str      # "contango" | "backwardation"
    vix_percentile: float        # vs 1-year

    # Survey Sentiment
    aaii_bullish: float
    aaii_bearish: float
    aaii_neutral: float
    aaii_bull_bear_spread: float

    # Fear & Greed
    fear_greed_value: int        # 0-100
    fear_greed_label: str        # "Extreme Fear" to "Extreme Greed"
    fear_greed_1w_ago: int
    fear_greed_1m_ago: int

    # Social Sentiment
    reddit_sentiment: float      # -1 to 1
    twitter_sentiment: float
    trending_tickers: List[str]

    # Positioning
    spy_short_interest: float
    qqq_short_interest: float
    most_shorted: List[str]

    # Insider Activity
    insider_buy_sell_ratio: float
    notable_insider_buys: List[Dict]
    notable_insider_sells: List[Dict]

    # Overall
    composite_sentiment: float   # -1 (extreme fear) to 1 (extreme greed)
    contrarian_signal: str       # "buy" | "sell" | "none"
    notes: List[str]
```

### API Interface

```python
# src/data/pipeline/sentiment.py

class SentimentAnalyzer:
    def __init__(self):
        pass

    def get_sentiment(self) -> SentimentIndicators:
        """Get current sentiment snapshot."""

    def get_put_call(self) -> Dict:
        """Get put/call ratio analysis."""

    def get_fear_greed(self) -> Dict:
        """Get CNN Fear & Greed index."""

    def get_social_sentiment(self, symbol: str = None) -> Dict:
        """Get social media sentiment."""

    def get_insider_activity(self, symbol: str = None) -> List[Dict]:
        """Get recent insider trades."""

    def get_contrarian_signals(self) -> List[str]:
        """Get contrarian trade signals from sentiment extremes."""
```

---

## 8. Economic & Earnings Calendar

### Problem
Knew SLB earnings were Jan 23 but didn't have systematic calendar integration. Could miss catalysts.

### Specification

```
Location: src/data/calendars/
Update Frequency: Daily refresh + real-time earnings alerts
```

### Data Sources

| Calendar | Source | Content |
|----------|--------|---------|
| Earnings | Yahoo Finance, Earnings Whispers | Earnings dates, estimates |
| Economic | FRED, Investing.com | Fed meetings, jobs, CPI, etc. |
| Dividends | Yahoo Finance | Ex-dates, amounts |
| Options Expiry | Manual | Monthly, weekly expiry dates |

### Output Schema

```python
@dataclass
class EarningsEvent:
    symbol: str
    date: date
    time: str                    # "BMO" | "AMC" | "DMH"
    eps_estimate: float
    eps_actual: float = None
    revenue_estimate: float
    revenue_actual: float = None
    surprise_pct: float = None
    guidance: str = None

@dataclass
class EconomicEvent:
    name: str
    date: datetime
    importance: str              # "HIGH" | "MEDIUM" | "LOW"
    previous: str
    forecast: str
    actual: str = None
    impact: str                  # "bullish" | "bearish" | "neutral"

@dataclass
class Calendar:
    date: date

    # Portfolio Events
    portfolio_earnings: List[EarningsEvent]
    portfolio_dividends: List[Dict]
    portfolio_expiries: List[Dict]

    # Watchlist Events
    watchlist_earnings: List[EarningsEvent]

    # Market Events
    economic_events: List[EconomicEvent]
    fed_speakers: List[Dict]
    options_expiry: bool         # Is it monthly/weekly expiry?

    # Summary
    risk_events: List[str]       # High-impact events
    notes: List[str]
```

### API Interface

```python
# src/data/calendars/calendar_manager.py

class CalendarManager:
    def __init__(self, portfolio: List[str], watchlist: List[str]):
        pass

    def get_today(self) -> Calendar:
        """Get today's calendar."""

    def get_week(self) -> List[Calendar]:
        """Get this week's calendar."""

    def get_earnings(self, symbol: str) -> EarningsEvent:
        """Get next earnings for symbol."""

    def get_economic_events(self, days_ahead: int = 7) -> List[EconomicEvent]:
        """Get upcoming economic events."""

    def get_portfolio_catalysts(self) -> List[Dict]:
        """Get all upcoming catalysts for portfolio."""
```

### Output Format (for LLM)

```
CALENDAR - Week of Jan 6, 2026
════════════════════════════════════════

TODAY (Mon Jan 6):
  Economic: ISM Services PMI (10am) - HIGH importance
  Fed: No speakers
  Options: None

TOMORROW (Tue Jan 7):
  Economic: JOLTS Job Openings (10am) - MEDIUM

WED Jan 8:
  Economic: ADP Employment (8:15am) - MEDIUM
  Fed: Fed Minutes Released (2pm) - HIGH

PORTFOLIO EARNINGS:
  Jan 21: HAL (BMO) - EPS est: $0.68
  Jan 23: SLB (BMO) - EPS est: $0.89 ⭐ KEY CATALYST
  Jan 31: XOM (BMO) - EPS est: $1.92

OPTIONS EXPIRING:
  Feb 6: SLB $44 calls (5), SLB $46 calls (2), GLD $409 calls (2)
         31 DTE - Theta accelerating

⚠️ RISK EVENTS:
  - Fed Minutes Wed could move markets
  - SLB earnings in 17 days - key for thesis
```

---

## 9. Position Risk Monitor

### Problem
Didn't have consolidated view of portfolio risk - correlations, concentration, Greeks exposure, etc.

### Specification

```
Location: src/risk/position_monitor.py
Update Frequency: Every 15 minutes
```

### Output Schema

```python
@dataclass
class PositionRisk:
    symbol: str
    position_type: str           # "equity" | "option"
    market_value: float
    weight_pct: float

    # Price Risk
    var_1d_95: float             # 1-day 95% VaR
    var_1d_99: float
    max_loss: float              # Worst case

    # For Options
    delta_exposure: float
    theta_exposure: float
    gamma_exposure: float
    vega_exposure: float

    # Correlation
    correlation_to_spy: float
    correlation_to_portfolio: float

    # Risk Flags
    flags: List[str]             # ["HIGH_CONCENTRATION", "CORRELATED", etc.]

@dataclass
class PortfolioRisk:
    timestamp: datetime

    # Portfolio Value
    total_equity: float
    total_options: float
    total_value: float
    cash: float

    # Concentration
    largest_position: str
    largest_position_pct: float
    top_5_concentration: float
    sector_concentration: Dict[str, float]

    # Correlation Risk
    avg_correlation: float
    correlation_matrix: Dict     # Simplified
    diversification_score: float # 0-100, higher = better diversified

    # Greeks Exposure (Options)
    total_delta: float
    total_theta_daily: float     # Daily $ at risk from theta
    total_vega: float
    total_gamma: float

    # VaR
    portfolio_var_1d_95: float
    portfolio_var_1d_99: float

    # Drawdown
    current_drawdown: float
    max_drawdown_30d: float

    # Limits Status
    limits: Dict[str, Dict]      # limit name -> {current, limit, status}
    violations: List[str]
    warnings: List[str]

    # Position Details
    positions: List[PositionRisk]

    # Recommendations
    reduce_positions: List[str]  # Positions to consider reducing
    hedge_suggestions: List[str]
    notes: List[str]
```

### API Interface

```python
# src/risk/position_monitor.py

class PositionRiskMonitor:
    def __init__(self, risk_limits: Dict):
        """
        risk_limits: {
            'max_position_pct': 25,
            'max_sector_pct': 50,
            'max_daily_loss_pct': 5,
            'max_correlation': 0.8,
        }
        """

    def get_portfolio_risk(self) -> PortfolioRisk:
        """Full portfolio risk assessment."""

    def get_position_risk(self, symbol: str) -> PositionRisk:
        """Risk for single position."""

    def check_limits(self) -> Dict:
        """Check all risk limits."""

    def get_correlations(self) -> Dict:
        """Get correlation matrix."""

    def calculate_var(self) -> Dict:
        """Calculate Value at Risk."""

    def get_recommendations(self) -> List[str]:
        """Get risk reduction recommendations."""
```

### Output Format (for LLM)

```
PORTFOLIO RISK REPORT - 2:30 PM ET
════════════════════════════════════════

VALUE: $94,160.92
  Equity: $71,527 (76%)
  Options: $9,229 (10%)
  Cash: $13,404 (14%)

CONCENTRATION:
  Largest Position: SLB 17.1% ⚠️ (limit 25%)
  Top 5: 43.2%
  Energy Sector: 39.5% ✅ (limit 50%)

CORRELATION:
  Avg Correlation: 0.62 (moderate)
  SLB-HAL: 0.89 (high) ⚠️
  SLB-XLE: 0.94 (high) ⚠️
  Diversification Score: 45/100 (needs improvement)

OPTIONS GREEKS:
  Net Delta: +$4,200 (bullish exposure)
  Daily Theta: -$85 (losing $85/day to decay)
  Vega: +$320 (long volatility)

VALUE AT RISK (95% confidence):
  1-Day VaR: $2,100 (2.2% of portfolio)
  Max Loss (options): $9,229 (all options worthless)

LIMIT STATUS:
  ✅ Position size: 17.1% < 25%
  ✅ Sector exposure: 39.5% < 50%
  ⚠️ Correlation: SLB/HAL 0.89 > 0.80 threshold
  ✅ Daily loss: 2.5% < 5%

RECOMMENDATIONS:
  1. Consider reducing HAL further (high correlation with SLB)
  2. Add uncorrelated position (GLD doing well)
  3. Monitor theta decay on SLB options ($40/day)
```

---

## 10. Implementation Priority

### Phase 1 - Critical (This Week)
| Component | Effort | Impact | Priority |
|-----------|--------|--------|----------|
| Alert System | Medium | High | 1 |
| Morning Open Protocol | Low | High | 2 |
| Intraday Technicals (basic) | Medium | High | 3 |

### Phase 2 - High Value (Next 2 Weeks)
| Component | Effort | Impact | Priority |
|-----------|--------|--------|----------|
| Live News Daemon | Medium | High | 4 |
| Options Analytics | High | High | 5 |
| Sector/Breadth | Medium | Medium | 6 |

### Phase 3 - Nice to Have (Month)
| Component | Effort | Impact | Priority |
|-----------|--------|--------|----------|
| Sentiment Indicators | High | Medium | 7 |
| Calendar Integration | Low | Medium | 8 |
| Position Risk Monitor | High | Medium | 9 |

---

## Integration with Existing System

### Morning Workflow Enhanced

```
6:00 AM  - /morning-briefing (existing)
           + News Daemon summary
           + Calendar events
           + Sentiment snapshot

7:00 AM  - /trade-decision (existing)
           + Options analytics
           + Sector positioning

9:35 AM  - NEW: Morning Open Protocol
           + Gap analysis
           + Plan confirmation/modification

9:30-4:00 - NEW: Continuous monitoring
           + Alert system active
           + Technicals updated every 5 min
           + News checked every 30 min

3:00 PM  - Power Hour Review
           + Position risk report
           + EOD recommendations

4:30 PM  - /eod-review (existing)
           + Full day analysis
           + Learning loop update
```

### File Structure

```
src/
├── data/
│   ├── sources/
│   │   └── realtime/
│   │       ├── news_daemon.py
│   │       └── social_sentiment.py
│   ├── pipeline/
│   │   ├── intraday_technicals.py
│   │   ├── options_analytics.py
│   │   ├── market_breadth.py
│   │   └── sentiment.py
│   └── calendars/
│       └── calendar_manager.py
├── alerts/
│   ├── alert_manager.py
│   └── alert_types.py
├── risk/
│   └── position_monitor.py
└── decision/
    └── morning_open.py
```

---

## Data Storage

All real-time data stored in `~/quant_results/realtime/`:

```
~/quant_results/realtime/
├── news/
│   └── 2026-01-06/
│       ├── news_0930.json
│       └── ...
├── technicals/
│   └── 2026-01-06/
│       ├── SLB_5m.json
│       └── ...
├── alerts/
│   └── 2026-01-06.json
├── breadth/
│   └── 2026-01-06.json
├── sentiment/
│   └── 2026-01-06.json
└── open_assessments/
    └── 2026-01-06.json
```

---

## Summary

This specification addresses the key gaps identified during live trading:

1. **News**: Real-time news monitoring with portfolio relevance filtering
2. **Technicals**: Full intraday technical analysis beyond just price
3. **Options**: Greeks, IV analysis, and decay projections
4. **Open Protocol**: Fast assessment at market open to confirm/modify plan
5. **Alerts**: Automated monitoring with configurable thresholds
6. **Breadth**: Sector rotation and market regime context
7. **Sentiment**: Positioning and sentiment indicators for contrarian signals
8. **Calendar**: Earnings, economic events, and catalyst tracking
9. **Risk**: Portfolio-level risk monitoring and limit checking

Combined, these tools would provide comprehensive real-time context for better intraday trading decisions.
