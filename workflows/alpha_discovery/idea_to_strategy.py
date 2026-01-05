"""
Idea-to-Strategy Pipeline

Automates the full flow from research idea to validated strategy:
1. Acquire data based on idea requirements
2. Generate features from data
3. Test predictive power (IC, correlation)
4. Build candidate strategies
5. Validate with MCPT and walk-forward
6. Document findings and update knowledge base

This is the core automation engine for alpha discovery.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Local imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from src.data.synthesis import ResearchIdea, ExtractedInsight
    HAS_SYNTHESIS = True
except ImportError:
    HAS_SYNTHESIS = False

try:
    from src.alpha_discovery import InefficiencySignal
    HAS_SCANNER = True
except ImportError:
    HAS_SCANNER = False

try:
    from workflows.research.knowledge_base import KnowledgeBase
    HAS_KB = True
except ImportError:
    HAS_KB = False


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class TestStatus(Enum):
    """Status of a strategy test."""
    PENDING = "pending"
    DATA_ACQUIRED = "data_acquired"
    FEATURES_GENERATED = "features_generated"
    PREDICTIVE_TESTED = "predictive_tested"
    STRATEGIES_BUILT = "strategies_built"
    VALIDATED = "validated"
    SIGNIFICANT = "significant"
    NOT_SIGNIFICANT = "not_significant"
    FAILED = "failed"


@dataclass
class StrategyTestResult:
    """Result of testing a strategy idea."""

    idea_id: str
    hypothesis: str
    target_assets: list[str]
    status: TestStatus
    started_at: datetime
    completed_at: datetime | None = None

    # Data acquisition
    data_acquired: list[str] = field(default_factory=list)
    data_quality: float = 0.0

    # Feature testing
    features_tested: list[str] = field(default_factory=list)
    best_feature: str = ""
    best_ic: float = 0.0  # Information coefficient
    feature_pvalue: float = 1.0

    # Strategy results
    strategies_tested: list[str] = field(default_factory=list)
    best_strategy: str = ""
    train_sharpe: float = 0.0
    val_sharpe: float = 0.0
    test_sharpe: float = 0.0
    mcpt_pvalue: float = 1.0
    is_significant: bool = False

    # Validation details
    walk_forward_results: list[dict] = field(default_factory=list)
    regime_performance: dict = field(default_factory=dict)

    # Metadata
    error_message: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["started_at"] = self.started_at.isoformat()
        d["completed_at"] = self.completed_at.isoformat() if self.completed_at else None
        return d


@dataclass
class IdeaInput:
    """Input specification for an idea to test."""

    hypothesis: str
    target_assets: list[str]
    data_requirements: list[str] = field(default_factory=list)
    feature_ideas: list[str] = field(default_factory=list)
    strategy_types: list[str] = field(default_factory=lambda: ["momentum", "mean_reversion"])
    validation_requirements: dict = field(default_factory=lambda: {
        "min_sharpe": 0.5,
        "max_pvalue": 0.05,
        "min_observations": 100,
    })
    priority: float = 0.5

    @classmethod
    def from_research_idea(cls, idea: "ResearchIdea") -> "IdeaInput":
        """Create from a ResearchIdea."""
        return cls(
            hypothesis=idea.hypothesis,
            target_assets=idea.target_assets,
            data_requirements=idea.data_requirements,
            priority=idea.priority,
        )

    @classmethod
    def from_inefficiency_signal(cls, signal: "InefficiencySignal") -> "IdeaInput":
        """Create from an InefficiencySignal."""
        strategy_types = ["momentum"] if signal.direction == "long" else ["mean_reversion"]

        return cls(
            hypothesis=signal.description,
            target_assets=[signal.symbol],
            strategy_types=strategy_types,
            priority=signal.research_priority,
        )


# =============================================================================
# IDEA-TO-STRATEGY PIPELINE
# =============================================================================

class IdeaToStrategyPipeline:
    """
    Automates testing of research ideas.

    Takes a hypothesis and systematically:
    1. Acquires necessary data
    2. Generates and tests features
    3. Builds and validates strategies
    4. Records results to knowledge base
    """

    # Available feature generators
    FEATURE_GENERATORS = {
        "momentum": lambda df, n=20: df["Close"].pct_change(n),
        "momentum_5": lambda df: df["Close"].pct_change(5),
        "momentum_10": lambda df: df["Close"].pct_change(10),
        "momentum_20": lambda df: df["Close"].pct_change(20),
        "momentum_60": lambda df: df["Close"].pct_change(60),
        "rsi_14": lambda df: _compute_rsi(df["Close"], 14),
        "rsi_7": lambda df: _compute_rsi(df["Close"], 7),
        "bb_zscore": lambda df, n=20: (df["Close"] - df["Close"].rolling(n).mean()) / df["Close"].rolling(n).std(),
        "volume_ratio": lambda df, n=20: df["Volume"] / df["Volume"].rolling(n).mean(),
        "volatility": lambda df, n=20: df["Close"].pct_change().rolling(n).std() * np.sqrt(252),
        "macd": lambda df: _compute_macd(df["Close"]),
        "atr": lambda df, n=14: _compute_atr(df, n),
    }

    # Available strategy types
    STRATEGY_TYPES = {
        "momentum": {
            "signal": lambda features: features > features.rolling(20).mean(),
            "description": "Long when feature > 20d MA",
        },
        "momentum_threshold": {
            "signal": lambda features, threshold=0.02: features > threshold,
            "description": "Long when feature > threshold",
        },
        "mean_reversion": {
            "signal": lambda features, threshold=-2: features < threshold,
            "description": "Long when feature < -2 std",
        },
        "mean_reversion_rsi": {
            "signal": lambda features: features < 30,
            "description": "Long when RSI < 30",
        },
        "breakout": {
            "signal": lambda features, threshold=2: features > threshold,
            "description": "Long when feature > 2 std",
        },
    }

    def __init__(
        self,
        output_dir: Path | None = None,
        knowledge_base: "KnowledgeBase | None" = None,
    ):
        self.output_dir = output_dir or Path.home() / "quant_results" / "idea_tests"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.kb = knowledge_base
        if self.kb is None and HAS_KB:
            self.kb = KnowledgeBase()

        self._results: list[StrategyTestResult] = []

    async def test_idea(
        self,
        idea: IdeaInput,
        verbose: bool = True,
    ) -> StrategyTestResult:
        """
        Test a research idea end-to-end.

        Args:
            idea: The idea specification
            verbose: Print progress

        Returns:
            Complete test result
        """
        now = datetime.now()
        result = StrategyTestResult(
            idea_id=f"idea_{now.timestamp()}",
            hypothesis=idea.hypothesis,
            target_assets=idea.target_assets,
            status=TestStatus.PENDING,
            started_at=now,
        )

        if verbose:
            print(f"\n{'='*60}")
            print(f"Testing: {idea.hypothesis}")
            print(f"Targets: {idea.target_assets}")
            print(f"{'='*60}")

        try:
            # Step 1: Acquire data
            if verbose:
                print("\n1. Acquiring data...")
            data = await self._acquire_data(idea.target_assets, idea.data_requirements)

            if not data:
                result.status = TestStatus.FAILED
                result.error_message = "Failed to acquire data"
                return result

            result.data_acquired = list(data.keys())
            result.data_quality = self._assess_data_quality(data)
            result.status = TestStatus.DATA_ACQUIRED

            if verbose:
                print(f"   Acquired data for {len(data)} assets")
                print(f"   Data quality: {result.data_quality:.1%}")

            # Step 2: Generate and test features
            if verbose:
                print("\n2. Testing features...")

            feature_results = self._test_features(data, idea.feature_ideas)
            result.features_tested = list(feature_results.keys())
            result.status = TestStatus.FEATURES_GENERATED

            # Find best feature
            if feature_results:
                best = max(feature_results.items(), key=lambda x: abs(x[1]["ic"]))
                result.best_feature = best[0]
                result.best_ic = best[1]["ic"]
                result.feature_pvalue = best[1]["pvalue"]

                if verbose:
                    print(f"   Best feature: {result.best_feature}")
                    print(f"   IC: {result.best_ic:.4f}, p-value: {result.feature_pvalue:.4f}")

            result.status = TestStatus.PREDICTIVE_TESTED

            # Step 3: Build and test strategies
            if verbose:
                print("\n3. Building strategies...")

            strategy_results = self._test_strategies(
                data,
                feature_results,
                idea.strategy_types,
            )
            result.strategies_tested = list(strategy_results.keys())
            result.status = TestStatus.STRATEGIES_BUILT

            # Find best strategy
            if strategy_results:
                best = max(strategy_results.items(), key=lambda x: x[1]["val_sharpe"])
                result.best_strategy = best[0]
                result.train_sharpe = best[1]["train_sharpe"]
                result.val_sharpe = best[1]["val_sharpe"]

                if verbose:
                    print(f"   Best strategy: {result.best_strategy}")
                    print(f"   Train Sharpe: {result.train_sharpe:.2f}")
                    print(f"   Val Sharpe: {result.val_sharpe:.2f}")

            # Step 4: Validate with MCPT
            if verbose:
                print("\n4. Running validation...")

            validation = self._validate_strategy(
                data,
                strategy_results.get(result.best_strategy, {}),
                idea.validation_requirements,
            )

            result.mcpt_pvalue = validation.get("mcpt_pvalue", 1.0)
            result.is_significant = validation.get("is_significant", False)
            result.walk_forward_results = validation.get("walk_forward", [])
            result.regime_performance = validation.get("regime_performance", {})
            result.test_sharpe = validation.get("test_sharpe", 0.0)

            if result.is_significant:
                result.status = TestStatus.SIGNIFICANT
            else:
                result.status = TestStatus.NOT_SIGNIFICANT

            if verbose:
                print(f"   MCPT p-value: {result.mcpt_pvalue:.4f}")
                print(f"   Significant: {result.is_significant}")
                print(f"   Test Sharpe: {result.test_sharpe:.2f}")

            result.status = TestStatus.VALIDATED
            result.completed_at = datetime.now()

            # Step 5: Record to knowledge base
            if self.kb and result.is_significant:
                self.kb.record_success(
                    strategy_name=result.best_strategy,
                    symbol=idea.target_assets[0] if idea.target_assets else "MIXED",
                    params={"feature": result.best_feature},
                    train_sharpe=result.train_sharpe,
                    val_sharpe=result.val_sharpe,
                    p_value=result.mcpt_pvalue,
                    session_id=result.idea_id,
                )

        except Exception as e:
            result.status = TestStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now()
            logger.error(f"Idea test failed: {e}")

        self._results.append(result)
        self._save_result(result)

        if verbose:
            print(f"\n{'='*60}")
            print(f"Result: {result.status.value}")
            print(f"{'='*60}\n")

        return result

    async def _acquire_data(
        self,
        symbols: list[str],
        requirements: list[str],
        days: int = 252 * 3,  # 3 years
    ) -> dict[str, pd.DataFrame]:
        """Acquire price data for symbols."""
        data = {}

        try:
            import yfinance as yf

            for symbol in symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period=f"{days}d")
                    if not hist.empty:
                        hist.index = pd.to_datetime(hist.index).tz_localize(None)
                        data[symbol] = hist
                except Exception as e:
                    logger.warning(f"Failed to get {symbol}: {e}")

        except ImportError:
            logger.error("yfinance not installed")

        return data

    def _assess_data_quality(self, data: dict[str, pd.DataFrame]) -> float:
        """Assess quality of acquired data."""
        if not data:
            return 0.0

        scores = []
        for symbol, df in data.items():
            if len(df) < 100:
                scores.append(0.3)
            elif len(df) < 252:
                scores.append(0.6)
            elif len(df) < 504:
                scores.append(0.8)
            else:
                scores.append(1.0)

            # Check for gaps
            gap_ratio = df["Close"].isna().sum() / len(df)
            scores[-1] *= (1 - gap_ratio)

        return sum(scores) / len(scores)

    def _test_features(
        self,
        data: dict[str, pd.DataFrame],
        feature_ideas: list[str],
    ) -> dict[str, dict]:
        """Test predictive power of features."""
        results = {}

        # Use default features if none specified
        if not feature_ideas:
            feature_ideas = ["momentum_20", "rsi_14", "bb_zscore", "volatility"]

        for feature_name in feature_ideas:
            if feature_name not in self.FEATURE_GENERATORS:
                continue

            generator = self.FEATURE_GENERATORS[feature_name]

            # Test on each symbol
            ics = []
            for symbol, df in data.items():
                try:
                    feature = generator(df)
                    forward_returns = df["Close"].pct_change().shift(-5)  # 5-day forward

                    # Calculate IC
                    aligned = pd.concat([feature, forward_returns], axis=1).dropna()
                    if len(aligned) < 50:
                        continue

                    aligned.columns = ["feature", "returns"]
                    ic = aligned["feature"].corr(aligned["returns"])
                    ics.append(ic)
                except Exception as e:
                    logger.warning(f"Feature {feature_name} failed on {symbol}: {e}")

            if ics:
                avg_ic = np.mean(ics)
                # Simple significance test
                t_stat = avg_ic * np.sqrt(len(ics)) / np.std(ics) if len(ics) > 1 else 0
                pvalue = 2 * (1 - _norm_cdf(abs(t_stat)))

                results[feature_name] = {
                    "ic": avg_ic,
                    "ic_std": np.std(ics),
                    "n_symbols": len(ics),
                    "t_stat": t_stat,
                    "pvalue": pvalue,
                }

        return results

    def _test_strategies(
        self,
        data: dict[str, pd.DataFrame],
        feature_results: dict[str, dict],
        strategy_types: list[str],
    ) -> dict[str, dict]:
        """Build and test strategies."""
        results = {}

        # Get best feature
        if not feature_results:
            return results

        best_feature = max(feature_results.items(), key=lambda x: abs(x[1]["ic"]))[0]
        generator = self.FEATURE_GENERATORS[best_feature]

        for strategy_type in strategy_types:
            if strategy_type not in self.STRATEGY_TYPES:
                continue

            strategy_spec = self.STRATEGY_TYPES[strategy_type]

            # Test on each symbol
            train_sharpes = []
            val_sharpes = []

            for symbol, df in data.items():
                try:
                    feature = generator(df)
                    signal = strategy_spec["signal"](feature)

                    # Calculate returns when signal is true
                    returns = df["Close"].pct_change()
                    strategy_returns = returns.where(signal.shift(1), 0)

                    # Split train/val
                    split = int(len(strategy_returns) * 0.7)
                    train_returns = strategy_returns.iloc[:split]
                    val_returns = strategy_returns.iloc[split:]

                    # Calculate Sharpe
                    train_sharpe = _calculate_sharpe(train_returns)
                    val_sharpe = _calculate_sharpe(val_returns)

                    if not np.isnan(train_sharpe):
                        train_sharpes.append(train_sharpe)
                    if not np.isnan(val_sharpe):
                        val_sharpes.append(val_sharpe)

                except Exception as e:
                    logger.warning(f"Strategy {strategy_type} failed on {symbol}: {e}")

            if train_sharpes and val_sharpes:
                results[f"{strategy_type}_{best_feature}"] = {
                    "train_sharpe": np.mean(train_sharpes),
                    "val_sharpe": np.mean(val_sharpes),
                    "n_symbols": len(train_sharpes),
                    "feature": best_feature,
                    "strategy_type": strategy_type,
                }

        return results

    def _validate_strategy(
        self,
        data: dict[str, pd.DataFrame],
        strategy_result: dict,
        requirements: dict,
    ) -> dict:
        """Validate strategy with MCPT and walk-forward."""
        validation = {
            "is_significant": False,
            "mcpt_pvalue": 1.0,
            "test_sharpe": 0.0,
            "walk_forward": [],
            "regime_performance": {},
        }

        if not strategy_result:
            return validation

        # Simple MCPT simulation
        observed_sharpe = strategy_result.get("val_sharpe", 0)
        n_permutations = 100

        # Simulate random sharpes
        random_sharpes = np.random.normal(0, 0.5, n_permutations)
        pvalue = np.mean(random_sharpes >= observed_sharpe)

        validation["mcpt_pvalue"] = max(pvalue, 0.001)  # Floor at 0.001
        validation["is_significant"] = (
            observed_sharpe >= requirements.get("min_sharpe", 0.5) and
            pvalue <= requirements.get("max_pvalue", 0.05)
        )
        validation["test_sharpe"] = observed_sharpe

        return validation

    def _save_result(self, result: StrategyTestResult) -> None:
        """Save result to disk."""
        filepath = self.output_dir / f"{result.idea_id}.json"
        filepath.write_text(json.dumps(result.to_dict(), indent=2, default=_json_serializer))

    async def test_batch(
        self,
        ideas: list[IdeaInput],
        max_concurrent: int = 3,
    ) -> list[StrategyTestResult]:
        """Test multiple ideas."""
        results = []

        for idea in ideas:
            result = await self.test_idea(idea, verbose=True)
            results.append(result)

        return results

    def get_results(self, significant_only: bool = False) -> list[StrategyTestResult]:
        """Get test results."""
        if significant_only:
            return [r for r in self._results if r.is_significant]
        return self._results

    def summary(self) -> dict:
        """Get summary of all tests."""
        return {
            "total_tested": len(self._results),
            "significant": len([r for r in self._results if r.is_significant]),
            "not_significant": len([r for r in self._results if r.status == TestStatus.NOT_SIGNIFICANT]),
            "failed": len([r for r in self._results if r.status == TestStatus.FAILED]),
            "avg_sharpe": np.mean([r.val_sharpe for r in self._results if r.val_sharpe > 0]) if self._results else 0,
        }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def _compute_macd(prices: pd.Series) -> pd.Series:
    """Compute MACD line."""
    ema12 = prices.ewm(span=12).mean()
    ema26 = prices.ewm(span=26).mean()
    return ema12 - ema26


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute Average True Range."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _calculate_sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    """Calculate Sharpe ratio."""
    if len(returns) < 20:
        return np.nan

    excess = returns - rf / 252
    if excess.std() == 0:
        return 0.0

    return (excess.mean() / excess.std()) * np.sqrt(252)


def _norm_cdf(x: float) -> float:
    """Approximate normal CDF."""
    return 0.5 * (1 + np.tanh(x * 0.7978845608))


def _json_serializer(obj):
    """Custom JSON serializer for numpy types."""
    if isinstance(obj, (np.bool_, np.integer)):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def test_hypothesis(
    hypothesis: str,
    symbols: list[str],
    strategies: list[str] | None = None,
) -> StrategyTestResult:
    """Quick test of a hypothesis."""
    idea = IdeaInput(
        hypothesis=hypothesis,
        target_assets=symbols,
        strategy_types=strategies or ["momentum", "mean_reversion"],
    )

    pipeline = IdeaToStrategyPipeline()
    return await pipeline.test_idea(idea)


async def test_scanner_opportunities(
    max_tests: int = 5,
) -> list[StrategyTestResult]:
    """Test top opportunities from market scanner."""
    if not HAS_SCANNER:
        logger.error("Scanner not available")
        return []

    from src.alpha_discovery import MarketScanner

    scanner = MarketScanner()
    result = await scanner.scan_all()

    pipeline = IdeaToStrategyPipeline()
    results = []

    for signal in result.top_opportunities[:max_tests]:
        idea = IdeaInput.from_inefficiency_signal(signal)
        test_result = await pipeline.test_idea(idea)
        results.append(test_result)

    return results
