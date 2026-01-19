# Implementation Plan: System Improvements

**Created**: 2026-01-11
**Status**: Ready for Implementation
**Estimated Effort**: 40-50 hours total

---

## Overview

This plan addresses all findings from the comprehensive system diagnostic:
- **P0 Critical Fixes** (5 items)
- **P1 Architecture Improvements** (5 items)
- **P2 Enhancements** (7 items)
- **Script Cleanup** (12 scripts to archive)
- **New Functionality** (3 features)

---

## Phase 1: P0 Critical Fixes (Week 1)

### 1.1 Fix Period Performance Estimates
**Priority**: P0 | **Effort**: 2 hours | **Impact**: HIGH

**Problem**: `src/synthesis/daemon.py:1039-1043` uses rough estimates:
```python
week_pnl = today_pnl * 3  # WRONG
month_pnl = today_pnl * 10  # WRONG
```

**Solution**:
1. Read portfolio history from `portfolio_history.json`
2. Calculate actual week/month performance from historical snapshots
3. Fall back to estimates only if history unavailable

**Files to modify**:
- `src/synthesis/daemon.py` - `_get_portfolio_snapshot()` method

**Implementation**:
```python
def _calculate_period_performance(self, history: list[dict], days: int) -> tuple[float, float]:
    """Calculate actual P&L over period from history."""
    if not history or len(history) < 2:
        return 0.0, 0.0

    cutoff = datetime.now() - timedelta(days=days)
    period_snapshots = [s for s in history if datetime.fromisoformat(s["timestamp"]) >= cutoff]

    if not period_snapshots:
        return 0.0, 0.0

    start_equity = period_snapshots[0]["equity"]
    end_equity = period_snapshots[-1]["equity"]
    pnl = end_equity - start_equity
    pnl_pct = (pnl / start_equity * 100) if start_equity > 0 else 0.0

    return pnl, pnl_pct
```

**Verification**:
```bash
PYTHONPATH=. python -c "
from src.synthesis.daemon import LiveDaemon
import asyncio
daemon = LiveDaemon()
state = asyncio.run(daemon.update_now())
print(f'Week P&L: {state.portfolio.week_pnl_pct:.2f}%')
print(f'Month P&L: {state.portfolio.month_pnl_pct:.2f}%')
"
```

---

### 1.2 Run MCPT on Top 20 Strategies
**Priority**: P0 | **Effort**: 4 hours | **Impact**: CRITICAL

**Problem**: Only 3/54 strategies (5.6%) have MCPT validation.

**Strategy Selection** (all categories equally):

**Technical (5)**:
1. bollinger_reversal (already validated for QCOM, MU)
2. momentum_breakout
3. mean_reversion_etf
4. trend_following
5. rsi_divergence

**Alternative Data (5)**:
1. congressional_cluster (insider_technical already validated for QQQ)
2. insider_follow
3. sentiment_contrarian
4. options_flow_follow
5. short_squeeze

**Sector/Event (5)**:
1. earnings_momentum
2. sector_rotation
3. energy_mean_reversion
4. fed_announcement
5. vix_mean_reversion

**Composite (5)**:
1. multi_signal_composite
2. regime_adaptive
3. factor_momentum
4. quality_momentum
5. value_momentum

**Validation Command**:
```bash
# For each strategy-symbol pair:
PYTHONPATH=. python scripts/validate_strategy.py \
    --strategy bollinger_reversal \
    --symbol AMD \
    --n_permutations 1000 \
    --plots
```

**Output**: Update `config/validated_strategies.yaml` with results:
```yaml
bollinger_reversal:
  QCOM: {sharpe: 3.14, p_value: 0.007, validated: true}
  MU: {sharpe: 2.93, p_value: 0.007, validated: true}
  AMD: {sharpe: X.XX, p_value: X.XXX, validated: true/false}
```

**Script to create**: `scripts/batch_validate_strategies.py`

---

### 1.3 Implement Conviction Decay
**Priority**: P0 | **Effort**: 3 hours | **Impact**: HIGH

**Problem**: `_compute_conviction_decay()` called but not implemented.

**Files to modify**:
- `src/synthesis/daemon.py` - implement `_compute_conviction_decay()`
- `src/synthesis/state.py` - `ConvictionDecayResult` already defined

**Implementation**:
```python
async def _compute_conviction_decay(self) -> list[ConvictionDecayResult]:
    """Compute conviction decay for theses without recent signpost activity."""
    results = []
    tracker = ThesisTracker(paths.theses)

    for thesis in tracker.get_active_theses():
        days_since_signpost = self._days_since_last_signpost(thesis)
        days_since_review = self._days_since_last_review(thesis)

        # Decay formula: 5% per week without signpost activity
        if days_since_signpost > 7:
            weeks_stale = days_since_signpost / 7
            decay_factor = 0.95 ** weeks_stale
            new_conviction = thesis.conviction * decay_factor

            severity = "critical" if new_conviction < 20 else "warning" if new_conviction < 40 else "info"

            results.append(ConvictionDecayResult(
                thesis_id=thesis.id,
                thesis_name=thesis.name,
                original_conviction=thesis.conviction,
                decayed_conviction=new_conviction,
                decay_reason=f"No signpost activity in {days_since_signpost} days",
                days_since_signpost=days_since_signpost,
                severity=severity,
            ))

    return results
```

**Verification**:
```bash
PYTHONPATH=. python -c "
from src.synthesis.state import UnifiedState
from src.core.paths import paths
state = UnifiedState.load(paths.live_state)
for decay in state.conviction_decay:
    print(f'{decay.thesis_name}: {decay.original_conviction:.0f}% -> {decay.decayed_conviction:.0f}%')
"
```

---

### 1.4 Fix Optional Field Defaults
**Priority**: P0 | **Effort**: 1 hour | **Impact**: MEDIUM

**Problem**: Some Optional fields lack `= None` defaults, causing TypeErrors.

**Files to modify**:
- `src/synthesis/state.py`

**Fields to fix** (search for `Optional[` without `= None`):
```python
# BEFORE
thesis_id: Optional[str]
distance_to_stop_pct: Optional[float]
distance_to_target_pct: Optional[float]

# AFTER
thesis_id: Optional[str] = None
distance_to_stop_pct: Optional[float] = None
distance_to_target_pct: Optional[float] = None
```

**Verification**:
```bash
PYTHONPATH=. python -c "
from src.synthesis.state import PositionSnapshot
# Should not raise TypeError
pos = PositionSnapshot(symbol='TEST', qty=100, avg_cost=10.0, current_price=11.0, market_value=1100.0)
print('Optional defaults work correctly')
"
```

---

### 1.5 Replace Broad Exception Handling (Top 10)
**Priority**: P0 | **Effort**: 2 hours | **Impact**: MEDIUM

**Problem**: 31 instances of `except Exception as e:` in daemon.py

**Priority locations** (fix top 10 most critical):

| Line | Method | Replace With |
|------|--------|--------------|
| 166 | `_get_market_snapshot` | `except (ConnectionError, httpx.HTTPError) as e` |
| 174 | `_get_sentiment_snapshot` | `except (ConnectionError, ValueError) as e` |
| 182 | `_get_portfolio_snapshot` | `except (ConnectionError, KeyError) as e` |
| 326 | Alpaca API call | `except alpaca.APIError as e` |
| 381 | Alpaca positions | `except alpaca.APIError as e` |
| 432 | Alpaca orders | `except alpaca.APIError as e` |
| 486 | Risk monitor | `except (ValueError, ZeroDivisionError) as e` |
| 908 | Signal aggregation | `except (ImportError, AttributeError) as e` |
| 1059 | Thesis computation | `except (FileNotFoundError, json.JSONDecodeError) as e` |
| 1118 | Learning log | `except (FileNotFoundError, json.JSONDecodeError) as e` |

**Verification**: Run daemon and check logs for proper error categorization.

---

## Phase 2: P1 Architecture Improvements (Week 2)

### 2.1 Add Reverse Query Methods
**Priority**: P1 | **Effort**: 3 hours | **Impact**: HIGH

**Files to modify**:
- `src/knowledge/thesis.py`
- `src/decision/decision_logger.py`

**Methods to add**:

```python
# In ThesisTracker
def get_theses_for_symbol(self, symbol: str) -> list[Thesis]:
    """Get all theses that include this symbol in positions."""
    return [t for t in self.get_active_theses() if symbol in t.positions]

# In DecisionLogger
def get_decisions_by_thesis(self, thesis_id: str, days: int = 30) -> list[TradingDecision]:
    """Get all decisions linked to a thesis."""
    decisions = []
    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        daily = self._load_day(date)
        decisions.extend([d for d in daily if d.thesis_id == thesis_id])
    return decisions

def get_decisions_by_symbol(self, symbol: str, days: int = 30) -> list[TradingDecision]:
    """Get all decisions for a symbol."""
    decisions = []
    for i in range(days):
        date = datetime.now() - timedelta(days=i)
        daily = self._load_day(date)
        decisions.extend([d for d in daily if d.symbol == symbol])
    return decisions
```

---

### 2.2 Add Decision Setup Type Tracking
**Priority**: P1 | **Effort**: 2 hours | **Impact**: HIGH

**Problem**: Cannot analyze "Which strategy types are profitable?"

**Files to modify**:
- `src/decision/decision_logger.py` - Add `setup_type` field to TradingDecision

**Implementation**:
```python
@dataclass
class TradingDecision:
    # ... existing fields ...
    setup_type: str = ""  # NEW: "mean_reversion", "momentum", "breakout", etc.
```

**Update `create_decision()`**:
```python
def create_decision(..., setup_type: str = "") -> TradingDecision:
```

**Infer setup type from AdversarialAgent**:
- File: `src/decision/adversary.py:616-631` already has `_infer_setup_type()`
- Store result in decision

---

### 2.3 Implement Signpost Alert Checking
**Priority**: P1 | **Effort**: 3 hours | **Impact**: MEDIUM

**Problem**: `_check_signpost_alerts()` not implemented.

**Files to modify**:
- `src/synthesis/daemon.py`

**Implementation**:
```python
async def _check_signpost_alerts(self) -> list[SignpostAlert]:
    """Check if any thesis signposts may have triggered."""
    alerts = []
    tracker = ThesisTracker(paths.theses)

    for thesis in tracker.get_active_theses():
        for i, signpost in enumerate(thesis.signposts):
            if signpost.status != "pending":
                continue

            # Check if signpost condition might be met
            # This is heuristic - Claude makes final determination
            trigger_likelihood = self._assess_signpost_likelihood(thesis, signpost)

            if trigger_likelihood > 0.5:
                alerts.append(SignpostAlert(
                    thesis_id=thesis.id,
                    thesis_name=thesis.name,
                    signpost_index=i,
                    signpost_description=signpost.description,
                    trigger_likelihood=trigger_likelihood,
                    evidence="Based on recent news/price action",
                ))

    return alerts
```

---

### 2.4 Refactor LiveDaemon - Extract Snapshot Builders
**Priority**: P1 | **Effort**: 4 hours | **Impact**: HIGH

**Problem**: LiveDaemon is 1,753 lines with 10+ hard dependencies.

**Solution**: Extract into separate builder classes

**New files to create**:
- `src/synthesis/builders/market_snapshot.py`
- `src/synthesis/builders/portfolio_snapshot.py`
- `src/synthesis/builders/thesis_snapshot.py`
- `src/synthesis/builders/signal_snapshot.py`

**Pattern**:
```python
# src/synthesis/builders/base.py
from abc import ABC, abstractmethod

class SnapshotBuilder(ABC):
    @abstractmethod
    async def build(self) -> dict:
        pass

# src/synthesis/builders/market_snapshot.py
class MarketSnapshotBuilder(SnapshotBuilder):
    def __init__(self, breadth_analyzer=None, sentiment_analyzer=None):
        self.breadth = breadth_analyzer or MarketBreadthAnalyzer()
        self.sentiment = sentiment_analyzer or SentimentAnalyzer()

    async def build(self) -> MarketSnapshot:
        # ... existing logic from daemon._get_market_snapshot()
```

**Updated daemon**:
```python
class LiveDaemon:
    def __init__(self,
                 market_builder: SnapshotBuilder = None,
                 portfolio_builder: SnapshotBuilder = None,
                 ...):
        self.market_builder = market_builder or MarketSnapshotBuilder()
        self.portfolio_builder = portfolio_builder or PortfolioSnapshotBuilder()
```

---

### 2.5 Add Sector Mapping Integration
**Priority**: P1 | **Effort**: 2 hours | **Impact**: MEDIUM

**Problem**: Only 40 symbols have hardcoded sector mappings.

**Solution**: Integrate with yfinance or cache from external source.

**Files to modify**:
- `src/synthesis/daemon.py` - `_get_sector()` method

**Implementation**:
```python
def _get_sector(self, symbol: str) -> str:
    """Get sector for a symbol with caching."""
    # Check cache first
    if symbol in self._sector_cache:
        return self._sector_cache[symbol]

    # Check static mapping
    if symbol in SECTOR_MAP:
        return SECTOR_MAP[symbol]

    # Fetch from yfinance and cache
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info
        sector = info.get("sector", "Unknown")
        self._sector_cache[symbol] = sector
        return sector
    except Exception:
        return "Unknown"
```

---

## Phase 3: P2 Enhancements (Week 3)

### 3.1 Fix Late Import in UnifiedState
**Effort**: 30 min

**File**: `src/synthesis/state.py:1302`
```python
# BEFORE (inside method)
from src.core.paths import paths

# AFTER (at module top)
from src.core.paths import paths
```

---

### 3.2 Remove Unused DecisionLogger
**Effort**: 15 min

**File**: `src/synthesis/daemon.py:577-579`
```python
# DELETE these lines
logger_instance = DecisionLogger()
```

---

### 3.3 Add Parse Error Logging
**Effort**: 1 hour

**File**: `src/synthesis/state.py` - All `from_dict()` methods

```python
# Add try/except with logging
try:
    validation = DataValidation.from_dict(data["validation"])
except (KeyError, ValueError) as e:
    logger.warning(f"Failed to parse validation: {e}")
    validation = None
```

---

### 3.4 Load Watchlist from Config
**Effort**: 30 min

**File**: `src/synthesis/daemon.py:83-88`

```python
# BEFORE
DEFAULT_WATCHLIST = ["SPY", "QQQ", ...]  # hardcoded

# AFTER
def _load_watchlist(self) -> list[str]:
    config_path = paths.base / "config" / "watchlist.yaml"
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f).get("symbols", DEFAULT_WATCHLIST)
    return DEFAULT_WATCHLIST
```

---

### 3.5 Mark ML Strategies as P3
**Effort**: 30 min

**Files**: `src/strategies/ml/*.py`

Add header comment to each:
```python
"""
ML Strategy - DEFERRED (P3)

Status: Placeholder - models not trained
TODO: Implement proper ML pipeline when prioritized
"""
```

---

### 3.6 Add Holiday Calendar to PDT Manager
**Effort**: 1 hour

**File**: `src/execution/pdt_manager.py`

```python
US_MARKET_HOLIDAYS = [
    # 2026 holidays
    "2026-01-01",  # New Year's Day
    "2026-01-20",  # MLK Day
    "2026-02-17",  # Presidents Day
    # ... etc
]

def _is_business_day(self, date: datetime) -> bool:
    if date.weekday() >= 5:
        return False
    if date.strftime("%Y-%m-%d") in US_MARKET_HOLIDAYS:
        return False
    return True
```

---

### 3.7 Ensure News Daemon Dependencies
**Effort**: 30 min

**File**: `src/synthesis/daemon.py:1473-1582`

Add check for news cache existence:
```python
async def _check_news_urgency(self) -> list[NewsUrgencyAlert]:
    news_cache = paths.live / "news_cache.json"
    if not news_cache.exists():
        logger.debug("News cache not found - news daemon may not be running")
        return []
    # ... rest of method
```

---

## Phase 4: Script Cleanup (Week 2)

### 4.1 Create Archive Directory
```bash
mkdir -p /home/nock/projects/quant_suite/archive/scripts
mkdir -p /home/nock/projects/quant_suite/archive/deprecated
```

### 4.2 Archive Redundant Scripts (12 files)

```bash
# Venezuela-specific monitors (use /thesis skill instead)
mv scripts/monitor_venezuela_positions.py archive/scripts/
mv scripts/monitor_venezuela_news.py archive/scripts/
mv scripts/monitor_loop.py archive/scripts/

# Research scripts (use /research skill instead)
mv scripts/advanced_strategy_builder.py archive/scripts/
mv scripts/build_and_evaluate_strategies.py archive/scripts/
mv scripts/test_research_system.py archive/scripts/
mv scripts/test_advanced_features.py archive/scripts/
mv scripts/run_experiments.py archive/scripts/

# Exploratory scripts
mv scripts/monday_alpha_scan.py archive/scripts/
mv scripts/monday_detailed_analysis.py archive/scripts/
mv scripts/expand_portfolio.py archive/scripts/
mv scripts/generate_venezuela_hypotheses.py archive/scripts/
```

### 4.3 Consolidate Validators

**Create**: `scripts/validate_strategy.py` with flags

```python
# Add CLI flags for specialized validation
parser.add_argument("--lead-lag", action="store_true", help="Lead-lag validation")
parser.add_argument("--commodity", action="store_true", help="Commodity mean reversion")
parser.add_argument("--options", action="store_true", help="Options strategy validation")
```

**Archive originals**:
```bash
mv scripts/validate_lead_lag_strategy.py archive/scripts/
mv scripts/validate_commodity_mean_rev.py archive/scripts/
mv scripts/validate_options_strategies.py archive/scripts/
```

### 4.4 Create Archive README
```bash
cat > archive/README.md << 'EOF'
# Archived Scripts

These scripts were archived on 2026-01-11 as part of codebase cleanup.

## Why Archived

- **Venezuela monitors**: Replaced by /thesis skill with signpost tracking
- **Research scripts**: Replaced by /research and /brainstorm skills
- **Specialized validators**: Consolidated into validate_strategy.py with flags
- **Exploratory scripts**: One-off research, no longer in active use

## To Restore

If needed, move back to scripts/ directory:
```bash
mv archive/scripts/SCRIPT_NAME.py scripts/
```
EOF
```

---

## Phase 5: New Functionality (Weeks 3-4)

### 5.1 Thesis Performance Attribution
**Priority**: HIGH | **Effort**: 6 hours

**Purpose**: Track P&L by thesis to answer "Which theses are profitable?"

**New file**: `src/knowledge/thesis_performance.py`

```python
@dataclass
class ThesisPerformanceMetrics:
    thesis_id: str
    thesis_name: str
    total_realized_pnl: float
    total_unrealized_pnl: float
    num_trades: int
    win_rate: float
    avg_hold_days: float
    best_trade: dict
    worst_trade: dict
    positions_active: list[str]

class ThesisPerformanceTracker:
    def __init__(self, thesis_dir: Path, decisions_dir: Path, learnings_dir: Path):
        self.thesis_tracker = ThesisTracker(thesis_dir)
        self.decision_logger = DecisionLogger(decisions_dir)
        self.learning_log = LearningLog(learnings_dir)

    def get_performance(self, thesis_id: str) -> ThesisPerformanceMetrics:
        """Calculate performance metrics for a thesis."""
        thesis = self.thesis_tracker.get_thesis(thesis_id)
        decisions = self.decision_logger.get_decisions_by_thesis(thesis_id)
        learnings = [l for l in self.learning_log.get_by_symbol(s)
                     for s in thesis.positions if l.thesis_id == thesis_id]

        # Calculate metrics
        realized_pnl = sum(l.realized_pnl for l in learnings)
        wins = [l for l in learnings if l.outcome == "win"]
        win_rate = len(wins) / len(learnings) if learnings else 0

        return ThesisPerformanceMetrics(
            thesis_id=thesis_id,
            thesis_name=thesis.name,
            total_realized_pnl=realized_pnl,
            # ... etc
        )

    def get_all_performance(self) -> list[ThesisPerformanceMetrics]:
        """Get performance for all active theses."""
        return [self.get_performance(t.id) for t in self.thesis_tracker.get_all_theses()]
```

**Integration**: Add to UnifiedState:
```python
# In state.py
thesis_performance: list[ThesisPerformanceMetrics] = field(default_factory=list)
```

---

### 5.2 Strategy Comparison Dashboard
**Priority**: HIGH | **Effort**: 8 hours

**Purpose**: Compare validated strategies by Sharpe, drawdown, p-value

**New file**: `src/evaluation/comparison/dashboard.py`

```python
@dataclass
class StrategyComparison:
    strategy_name: str
    symbol: str
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    mcpt_p_value: float
    total_return: float
    win_rate: float
    profit_factor: float
    validated: bool
    validation_date: datetime

class StrategyDashboard:
    def __init__(self, validated_strategies_path: Path):
        self.strategies_path = validated_strategies_path

    def load_comparisons(self) -> list[StrategyComparison]:
        """Load all validated strategy results."""
        with open(self.strategies_path) as f:
            data = yaml.safe_load(f)

        comparisons = []
        for strategy, symbols in data.items():
            for symbol, metrics in symbols.items():
                comparisons.append(StrategyComparison(
                    strategy_name=strategy,
                    symbol=symbol,
                    sharpe_ratio=metrics["sharpe"],
                    mcpt_p_value=metrics["p_value"],
                    validated=metrics["p_value"] < 0.05,
                    # ... etc
                ))
        return comparisons

    def rank_by_metric(self, metric: str = "sharpe_ratio") -> list[StrategyComparison]:
        """Rank strategies by a specific metric."""
        comparisons = self.load_comparisons()
        return sorted(comparisons, key=lambda x: getattr(x, metric), reverse=True)

    def get_validated_only(self) -> list[StrategyComparison]:
        """Get only MCPT-validated strategies."""
        return [c for c in self.load_comparisons() if c.validated]

    def generate_report(self) -> str:
        """Generate markdown comparison report."""
        validated = self.get_validated_only()

        lines = ["# Strategy Comparison Report", ""]
        lines.append("## Validated Strategies (MCPT p < 0.05)")
        lines.append("")
        lines.append("| Strategy | Symbol | Sharpe | Drawdown | p-value |")
        lines.append("|----------|--------|--------|----------|---------|")

        for s in sorted(validated, key=lambda x: x.sharpe_ratio, reverse=True):
            lines.append(f"| {s.strategy_name} | {s.symbol} | {s.sharpe_ratio:.2f} | {s.max_drawdown:.1f}% | {s.mcpt_p_value:.3f} |")

        return "\n".join(lines)
```

**New skill**: `.claude/skills/compare-strategies/SKILL.md`

---

### 5.3 Automated Promotion Pipeline
**Priority**: HIGH | **Effort**: 10 hours

**Purpose**: Test → Paper → Live with gates requiring MCPT validation

**New file**: `src/execution/promotion/pipeline.py`

```python
class PromotionStage(Enum):
    BACKTEST = "backtest"
    MCPT_VALIDATION = "mcpt_validation"
    PAPER_TRADING = "paper_trading"
    PAPER_REVIEW = "paper_review"
    LIVE_TRADING = "live_trading"

@dataclass
class PromotionCandidate:
    strategy_name: str
    symbol: str
    current_stage: PromotionStage
    backtest_sharpe: Optional[float] = None
    mcpt_p_value: Optional[float] = None
    paper_days: int = 0
    paper_pnl: float = 0.0
    paper_sharpe: Optional[float] = None
    promoted_to_live: bool = False
    promotion_date: Optional[datetime] = None
    rejection_reason: Optional[str] = None

class PromotionPipeline:
    """Manages strategy promotion from backtest to live trading."""

    GATES = {
        PromotionStage.MCPT_VALIDATION: {
            "min_sharpe": 1.0,
            "max_p_value": 0.05,
        },
        PromotionStage.PAPER_REVIEW: {
            "min_paper_days": 20,
            "min_paper_sharpe": 0.5,
            "max_paper_drawdown": 15.0,
        },
        PromotionStage.LIVE_TRADING: {
            "require_human_approval": True,
        },
    }

    def __init__(self, candidates_path: Path):
        self.candidates_path = candidates_path
        self.candidates: list[PromotionCandidate] = self._load_candidates()

    def add_candidate(self, strategy: str, symbol: str) -> PromotionCandidate:
        """Add new strategy to pipeline."""
        candidate = PromotionCandidate(
            strategy_name=strategy,
            symbol=symbol,
            current_stage=PromotionStage.BACKTEST,
        )
        self.candidates.append(candidate)
        self._save_candidates()
        return candidate

    def advance_stage(self, candidate: PromotionCandidate) -> bool:
        """Try to advance candidate to next stage."""
        gates = self.GATES.get(candidate.current_stage.next())

        if not self._check_gates(candidate, gates):
            return False

        candidate.current_stage = candidate.current_stage.next()
        self._save_candidates()
        return True

    def _check_gates(self, candidate: PromotionCandidate, gates: dict) -> bool:
        """Check if candidate passes all gates for next stage."""
        if "min_sharpe" in gates and candidate.backtest_sharpe < gates["min_sharpe"]:
            candidate.rejection_reason = f"Sharpe {candidate.backtest_sharpe:.2f} < {gates['min_sharpe']}"
            return False

        if "max_p_value" in gates and candidate.mcpt_p_value > gates["max_p_value"]:
            candidate.rejection_reason = f"p-value {candidate.mcpt_p_value:.3f} > {gates['max_p_value']}"
            return False

        # ... more gate checks
        return True

    def get_ready_for_paper(self) -> list[PromotionCandidate]:
        """Get candidates ready to start paper trading."""
        return [c for c in self.candidates
                if c.current_stage == PromotionStage.MCPT_VALIDATION
                and c.mcpt_p_value is not None
                and c.mcpt_p_value < 0.05]

    def get_ready_for_live(self) -> list[PromotionCandidate]:
        """Get candidates ready for live trading (pending approval)."""
        return [c for c in self.candidates
                if c.current_stage == PromotionStage.PAPER_REVIEW
                and c.paper_days >= 20
                and c.paper_sharpe >= 0.5]
```

**New skill**: `.claude/skills/promote/SKILL.md` (update existing)

**New cron job**: `scripts/cron_paper_trading_review.py`
- Daily check of paper trading performance
- Auto-advance candidates that meet gates
- Alert when candidates ready for live promotion

---

## Phase 6: Verification & Documentation (Week 4)

### 6.1 Run Full Validation Suite
```bash
# Validate all changes
PYTHONPATH=. python scripts/validate_data_flow.py

# Run strategy validation batch
PYTHONPATH=. python scripts/batch_validate_strategies.py

# Check promotion pipeline
PYTHONPATH=. python -c "
from src.execution.promotion.pipeline import PromotionPipeline
from src.core.paths import paths
pipeline = PromotionPipeline(paths.base / 'promotion_candidates.yaml')
print(f'Ready for paper: {len(pipeline.get_ready_for_paper())}')
print(f'Ready for live: {len(pipeline.get_ready_for_live())}')
"
```

### 6.2 Update Documentation
- Update `CLAUDE.md` with new features
- Update `DEVLOG.md` with implementation notes
- Create `docs/PROMOTION_PIPELINE.md`
- Create `docs/THESIS_PERFORMANCE.md`

### 6.3 Update Cron Jobs
```bash
PYTHONPATH=. python scripts/setup_cron.py --install
```

New jobs to add:
- `cron_thesis_signpost_check.py` - hourly
- `cron_paper_trading_review.py` - daily 5:30 PM

---

## Implementation Order Summary

### Week 1: P0 Critical Fixes
1. ✅ Fix period performance estimates (2h)
2. ✅ Create batch validation script (1h)
3. ✅ Run MCPT on top 20 strategies (4h)
4. ✅ Implement conviction decay (3h)
5. ✅ Fix optional field defaults (1h)
6. ✅ Replace broad exceptions (top 10) (2h)

### Week 2: P1 Architecture + Cleanup
1. ✅ Add reverse query methods (3h)
2. ✅ Add decision setup type tracking (2h)
3. ✅ Implement signpost alert checking (3h)
4. ✅ Archive redundant scripts (1h)
5. ✅ Consolidate validators (1h)
6. ✅ Add sector mapping integration (2h)

### Week 3: P2 Enhancements + New Features (Part 1)
1. ✅ P2 quick fixes (3h total)
2. ✅ Thesis Performance Attribution (6h)
3. ✅ Strategy Comparison Dashboard (8h)

### Week 4: New Features (Part 2) + Verification
1. ✅ Automated Promotion Pipeline (10h)
2. ✅ Run full validation suite (2h)
3. ✅ Update documentation (2h)
4. ✅ Update cron jobs (1h)

---

## Files to Create

| File | Purpose |
|------|---------|
| `scripts/batch_validate_strategies.py` | Validate multiple strategies |
| `src/synthesis/builders/base.py` | Snapshot builder base class |
| `src/synthesis/builders/market_snapshot.py` | Market data builder |
| `src/synthesis/builders/portfolio_snapshot.py` | Portfolio data builder |
| `src/knowledge/thesis_performance.py` | Thesis P&L tracking |
| `src/evaluation/comparison/dashboard.py` | Strategy comparison |
| `src/execution/promotion/pipeline.py` | Promotion pipeline |
| `scripts/cron_thesis_signpost_check.py` | Signpost monitoring |
| `scripts/cron_paper_trading_review.py` | Paper trading review |
| `config/validated_strategies.yaml` | Validation results |
| `config/watchlist.yaml` | Configurable watchlist |
| `archive/README.md` | Archive documentation |

## Files to Modify

| File | Changes |
|------|---------|
| `src/synthesis/daemon.py` | Period perf, conviction decay, exceptions |
| `src/synthesis/state.py` | Optional defaults, thesis performance |
| `src/knowledge/thesis.py` | Reverse query methods |
| `src/decision/decision_logger.py` | Setup type, reverse queries |
| `src/execution/pdt_manager.py` | Holiday calendar |
| `scripts/validate_strategy.py` | Consolidate validators |
| `scripts/setup_cron.py` | New cron jobs |
| `CLAUDE.md` | Documentation updates |
| `DEVLOG.md` | Implementation notes |

---

## Success Criteria

1. **Strategy Validation**: 20+ strategies have MCPT p-values documented
2. **Period Performance**: Week/month P&L calculated from actual history
3. **Conviction Decay**: Theses auto-decay when signposts not triggered
4. **Thesis Attribution**: Can answer "Which theses are profitable?"
5. **Promotion Pipeline**: Strategies flow from backtest → paper → live with gates
6. **Script Cleanup**: 12 scripts archived, validators consolidated
7. **Documentation**: All new features documented

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking changes to daemon | Test with paper trading first |
| Strategy validation takes too long | Parallelize with joblib |
| Archive breaks existing workflows | Keep archive accessible, document restore |
| New features introduce bugs | Comprehensive testing before merge |

---

## Notes

- ML strategies deferred to P3 (keep placeholders, mark as deferred)
- Regime-adaptive sizing not prioritized (can add later)
- All changes should be backward compatible with existing state.json
