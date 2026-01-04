"""Market regime detection and conditional evaluation.

Provides tools for:
- Detecting market regimes (bull, bear, sideways, high/low volatility)
- Evaluating strategy performance by regime
- Conditional backtesting
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

# Try to import HMM library
try:
    from hmmlearn import hmm
    HMM_AVAILABLE = True
except ImportError:
    HMM_AVAILABLE = False
    logger.info("hmmlearn not available, HMM regime detection disabled")


class RegimeType(str, Enum):
    """Types of market regimes."""

    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CRISIS = "crisis"
    RECOVERY = "recovery"
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current regime state with probabilities."""

    regime: RegimeType
    probability: float
    start_date: pd.Timestamp | None = None
    duration_days: int = 0
    characteristics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regime": self.regime.value,
            "probability": round(self.probability, 3),
            "start_date": self.start_date.strftime("%Y-%m-%d") if self.start_date else None,
            "duration_days": self.duration_days,
            "characteristics": {k: round(v, 4) for k, v in self.characteristics.items()},
        }


@dataclass
class RegimeAnalysis:
    """Complete regime analysis results."""

    regimes: pd.Series  # Regime labels for each date
    probabilities: pd.DataFrame | None  # Probability of each regime
    transitions: pd.DataFrame | None  # Transition matrix
    statistics: dict[str, dict[str, float]]  # Stats per regime
    current_regime: RegimeState | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_regime": self.current_regime.to_dict() if self.current_regime else None,
            "regime_distribution": self.regimes.value_counts().to_dict(),
            "statistics_by_regime": self.statistics,
            "n_transitions": int(np.sum(self.regimes != self.regimes.shift(1)) - 1) if len(self.regimes) > 1 else 0,
        }


class RuleBasedRegimeDetector:
    """
    Rule-based regime detector using technical indicators.

    Simple but interpretable approach for regime detection.
    """

    def __init__(
        self,
        trend_window: int = 50,
        volatility_window: int = 20,
        volatility_percentile_high: float = 75,
        volatility_percentile_low: float = 25,
        trend_threshold: float = 0.02,
    ):
        """
        Initialize rule-based detector.

        Args:
            trend_window: Window for trend calculation
            volatility_window: Window for volatility calculation
            volatility_percentile_high: Percentile for high volatility
            volatility_percentile_low: Percentile for low volatility
            trend_threshold: Threshold for trend classification
        """
        self.trend_window = trend_window
        self.volatility_window = volatility_window
        self.vol_high = volatility_percentile_high
        self.vol_low = volatility_percentile_low
        self.trend_threshold = trend_threshold

    def detect(self, data: pd.DataFrame) -> RegimeAnalysis:
        """
        Detect regimes from price data.

        Args:
            data: OHLCV DataFrame with DatetimeIndex

        Returns:
            RegimeAnalysis object
        """
        if "close" not in data.columns:
            raise ValueError("Data must have 'close' column")

        close = data["close"]
        returns = close.pct_change()

        # Compute indicators
        sma = close.rolling(self.trend_window).mean()
        trend = (close / sma - 1)

        volatility = returns.rolling(self.volatility_window).std() * np.sqrt(252)
        vol_expanding = volatility.expanding().apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
        )

        # Classify regimes
        regimes = pd.Series(index=data.index, dtype=object)

        for i, idx in enumerate(data.index):
            if pd.isna(trend.iloc[i]) or pd.isna(volatility.iloc[i]):
                regimes.iloc[i] = RegimeType.UNKNOWN.value
                continue

            t = trend.iloc[i]
            vol_pct = vol_expanding.iloc[i] if not pd.isna(vol_expanding.iloc[i]) else 50

            # Determine regime
            if vol_pct > 90:
                regimes.iloc[i] = RegimeType.CRISIS.value
            elif vol_pct > self.vol_high:
                regimes.iloc[i] = RegimeType.HIGH_VOLATILITY.value
            elif vol_pct < self.vol_low:
                regimes.iloc[i] = RegimeType.LOW_VOLATILITY.value
            elif t > self.trend_threshold:
                regimes.iloc[i] = RegimeType.BULL.value
            elif t < -self.trend_threshold:
                regimes.iloc[i] = RegimeType.BEAR.value
            else:
                regimes.iloc[i] = RegimeType.SIDEWAYS.value

        # Compute statistics per regime
        statistics = self._compute_regime_statistics(returns, regimes)

        # Current regime
        current_regime = self._get_current_regime(regimes, returns)

        return RegimeAnalysis(
            regimes=regimes,
            probabilities=None,
            transitions=self._compute_transition_matrix(regimes),
            statistics=statistics,
            current_regime=current_regime,
        )

    def _compute_regime_statistics(
        self,
        returns: pd.Series,
        regimes: pd.Series,
    ) -> dict[str, dict[str, float]]:
        """Compute statistics for each regime."""
        stats_dict = {}

        for regime in regimes.unique():
            if regime == RegimeType.UNKNOWN.value:
                continue

            mask = regimes == regime
            regime_returns = returns[mask].dropna()

            if len(regime_returns) < 5:
                continue

            stats_dict[regime] = {
                "count_days": int(mask.sum()),
                "pct_of_total": round(mask.sum() / len(regimes) * 100, 1),
                "mean_return_annual": round(regime_returns.mean() * 252, 4),
                "volatility_annual": round(regime_returns.std() * np.sqrt(252), 4),
                "sharpe_ratio": round(
                    (regime_returns.mean() / regime_returns.std()) * np.sqrt(252)
                    if regime_returns.std() > 0 else 0,
                    2
                ),
                "max_drawdown": round(self._compute_max_dd(regime_returns), 4),
                "win_rate": round((regime_returns > 0).mean(), 3),
            }

        return stats_dict

    def _compute_max_dd(self, returns: pd.Series) -> float:
        """Compute maximum drawdown."""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()

    def _compute_transition_matrix(self, regimes: pd.Series) -> pd.DataFrame:
        """Compute regime transition matrix."""
        unique_regimes = [r for r in regimes.unique() if r != RegimeType.UNKNOWN.value]

        if len(unique_regimes) < 2:
            return None

        # Count transitions
        transitions = pd.DataFrame(
            0,
            index=unique_regimes,
            columns=unique_regimes,
            dtype=float,
        )

        for i in range(1, len(regimes)):
            prev = regimes.iloc[i - 1]
            curr = regimes.iloc[i]
            if prev != RegimeType.UNKNOWN.value and curr != RegimeType.UNKNOWN.value:
                transitions.loc[prev, curr] += 1

        # Normalize to probabilities
        row_sums = transitions.sum(axis=1)
        transitions = transitions.div(row_sums, axis=0).fillna(0)

        return transitions

    def _get_current_regime(
        self,
        regimes: pd.Series,
        returns: pd.Series,
    ) -> RegimeState | None:
        """Get current regime state."""
        if len(regimes) == 0:
            return None

        current = regimes.iloc[-1]
        if current == RegimeType.UNKNOWN.value:
            return None

        # Find regime start
        start_idx = len(regimes) - 1
        while start_idx > 0 and regimes.iloc[start_idx - 1] == current:
            start_idx -= 1

        start_date = regimes.index[start_idx]
        duration = len(regimes) - start_idx

        # Compute characteristics
        regime_returns = returns.iloc[start_idx:].dropna()
        characteristics = {}
        if len(regime_returns) > 0:
            characteristics = {
                "mean_return": regime_returns.mean() * 252,
                "volatility": regime_returns.std() * np.sqrt(252),
                "cumulative_return": (1 + regime_returns).prod() - 1,
            }

        return RegimeState(
            regime=RegimeType(current),
            probability=1.0,
            start_date=start_date,
            duration_days=duration,
            characteristics=characteristics,
        )


class HMMRegimeDetector:
    """
    Hidden Markov Model regime detector.

    Uses Gaussian HMM to detect latent market regimes.
    """

    def __init__(
        self,
        n_regimes: int = 3,
        features: list[str] | None = None,
        n_iter: int = 100,
        random_state: int = 42,
    ):
        """
        Initialize HMM detector.

        Args:
            n_regimes: Number of hidden states
            features: Features to use (default: returns, volatility)
            n_iter: Number of EM iterations
            random_state: Random seed
        """
        if not HMM_AVAILABLE:
            raise ImportError("hmmlearn required for HMMRegimeDetector")

        self.n_regimes = n_regimes
        self.features = features or ["returns", "volatility"]
        self.n_iter = n_iter
        self.random_state = random_state
        self.model = None
        self._regime_mapping = {}

    def fit(self, data: pd.DataFrame) -> "HMMRegimeDetector":
        """
        Fit HMM to data.

        Args:
            data: OHLCV DataFrame

        Returns:
            Self
        """
        features = self._prepare_features(data)
        features_clean = features.dropna()

        self.model = hmm.GaussianHMM(
            n_components=self.n_regimes,
            covariance_type="full",
            n_iter=self.n_iter,
            random_state=self.random_state,
        )

        self.model.fit(features_clean.values)

        # Map regimes to interpretable labels
        self._map_regimes(features_clean)

        return self

    def detect(self, data: pd.DataFrame) -> RegimeAnalysis:
        """
        Detect regimes in data.

        Args:
            data: OHLCV DataFrame

        Returns:
            RegimeAnalysis object
        """
        if self.model is None:
            self.fit(data)

        features = self._prepare_features(data)
        features_clean = features.dropna()

        # Predict regimes
        hidden_states = self.model.predict(features_clean.values)
        probabilities = self.model.predict_proba(features_clean.values)

        # Map to regime types
        regimes = pd.Series(
            [self._regime_mapping.get(s, RegimeType.UNKNOWN.value) for s in hidden_states],
            index=features_clean.index,
        )

        # Expand to full index
        full_regimes = pd.Series(RegimeType.UNKNOWN.value, index=data.index)
        full_regimes.loc[regimes.index] = regimes

        # Create probability DataFrame
        prob_df = pd.DataFrame(
            probabilities,
            index=features_clean.index,
            columns=[self._regime_mapping.get(i, f"regime_{i}") for i in range(self.n_regimes)],
        )

        # Compute statistics
        returns = data["close"].pct_change()
        statistics = self._compute_statistics(returns, full_regimes)

        # Current regime
        current_regime = self._get_current_regime(
            regimes, prob_df, returns
        )

        return RegimeAnalysis(
            regimes=full_regimes,
            probabilities=prob_df,
            transitions=self._get_transition_matrix(),
            statistics=statistics,
            current_regime=current_regime,
        )

    def _prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare features for HMM."""
        close = data["close"]
        returns = close.pct_change()

        features_dict = {}

        if "returns" in self.features:
            features_dict["returns"] = returns

        if "volatility" in self.features:
            features_dict["volatility"] = returns.rolling(20).std()

        if "momentum" in self.features:
            features_dict["momentum"] = close.pct_change(20)

        if "trend" in self.features:
            sma = close.rolling(50).mean()
            features_dict["trend"] = (close / sma - 1)

        return pd.DataFrame(features_dict)

    def _map_regimes(self, features: pd.DataFrame) -> None:
        """Map hidden states to interpretable regime types."""
        hidden_states = self.model.predict(features.values)

        # Analyze each state
        state_stats = {}
        for state in range(self.n_regimes):
            mask = hidden_states == state
            if "returns" in features.columns:
                mean_ret = features.loc[mask, "returns"].mean()
                vol = features.loc[mask, "returns"].std() if "returns" in features.columns else 0
            else:
                mean_ret = 0
                vol = 0

            state_stats[state] = {"mean_return": mean_ret, "volatility": vol}

        # Sort by mean return and volatility
        sorted_by_return = sorted(state_stats.items(), key=lambda x: x[1]["mean_return"])
        sorted_by_vol = sorted(state_stats.items(), key=lambda x: x[1]["volatility"])

        # Assign labels
        if self.n_regimes == 2:
            # Simple bull/bear
            self._regime_mapping = {
                sorted_by_return[0][0]: RegimeType.BEAR.value,
                sorted_by_return[1][0]: RegimeType.BULL.value,
            }
        elif self.n_regimes == 3:
            # Bull/sideways/bear
            self._regime_mapping = {
                sorted_by_return[0][0]: RegimeType.BEAR.value,
                sorted_by_return[1][0]: RegimeType.SIDEWAYS.value,
                sorted_by_return[2][0]: RegimeType.BULL.value,
            }
        else:
            # Use volatility to distinguish
            for i, (state, _) in enumerate(sorted_by_return):
                if i < self.n_regimes // 3:
                    self._regime_mapping[state] = RegimeType.BEAR.value
                elif i >= 2 * self.n_regimes // 3:
                    self._regime_mapping[state] = RegimeType.BULL.value
                else:
                    self._regime_mapping[state] = RegimeType.SIDEWAYS.value

    def _compute_statistics(
        self,
        returns: pd.Series,
        regimes: pd.Series,
    ) -> dict[str, dict[str, float]]:
        """Compute statistics per regime."""
        stats_dict = {}

        for regime in regimes.unique():
            if regime == RegimeType.UNKNOWN.value:
                continue

            mask = regimes == regime
            regime_returns = returns[mask].dropna()

            if len(regime_returns) < 5:
                continue

            stats_dict[regime] = {
                "count_days": int(mask.sum()),
                "pct_of_total": round(mask.sum() / len(regimes) * 100, 1),
                "mean_return_annual": round(regime_returns.mean() * 252, 4),
                "volatility_annual": round(regime_returns.std() * np.sqrt(252), 4),
                "sharpe_ratio": round(
                    (regime_returns.mean() / regime_returns.std()) * np.sqrt(252)
                    if regime_returns.std() > 0 else 0,
                    2
                ),
            }

        return stats_dict

    def _get_transition_matrix(self) -> pd.DataFrame | None:
        """Get transition matrix from HMM."""
        if self.model is None:
            return None

        labels = [self._regime_mapping.get(i, f"regime_{i}") for i in range(self.n_regimes)]
        return pd.DataFrame(
            self.model.transmat_,
            index=labels,
            columns=labels,
        ).round(3)

    def _get_current_regime(
        self,
        regimes: pd.Series,
        probabilities: pd.DataFrame,
        returns: pd.Series,
    ) -> RegimeState | None:
        """Get current regime state."""
        if len(regimes) == 0:
            return None

        current = regimes.iloc[-1]
        prob = probabilities.iloc[-1].max()

        # Find regime start
        start_idx = len(regimes) - 1
        while start_idx > 0 and regimes.iloc[start_idx - 1] == current:
            start_idx -= 1

        return RegimeState(
            regime=RegimeType(current),
            probability=prob,
            start_date=regimes.index[start_idx],
            duration_days=len(regimes) - start_idx,
            characteristics={},
        )


class ConditionalEvaluator:
    """Evaluate strategy performance conditional on market regime."""

    def __init__(
        self,
        regime_detector: RuleBasedRegimeDetector | HMMRegimeDetector | None = None,
    ):
        """
        Initialize conditional evaluator.

        Args:
            regime_detector: Regime detector to use (default: rule-based)
        """
        self.detector = regime_detector or RuleBasedRegimeDetector()

    def evaluate(
        self,
        strategy_returns: pd.Series,
        market_data: pd.DataFrame,
        benchmark_returns: pd.Series | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate strategy performance by regime.

        Args:
            strategy_returns: Strategy returns
            market_data: Market OHLCV data for regime detection
            benchmark_returns: Optional benchmark returns

        Returns:
            Conditional evaluation results
        """
        # Detect regimes
        regime_analysis = self.detector.detect(market_data)
        regimes = regime_analysis.regimes

        # Align data
        aligned_regimes = regimes.reindex(strategy_returns.index)

        results = {
            "overall": self._compute_metrics(strategy_returns),
            "by_regime": {},
            "regime_analysis": regime_analysis.to_dict(),
        }

        # Evaluate per regime
        for regime in aligned_regimes.unique():
            if regime == RegimeType.UNKNOWN.value:
                continue

            mask = aligned_regimes == regime
            regime_returns = strategy_returns[mask].dropna()

            if len(regime_returns) < 10:
                continue

            regime_metrics = self._compute_metrics(regime_returns)

            # Compare to benchmark if available
            if benchmark_returns is not None:
                bench_regime = benchmark_returns.reindex(regime_returns.index).dropna()
                if len(bench_regime) > 0:
                    regime_metrics["vs_benchmark"] = {
                        "excess_return": round(
                            (regime_returns.mean() - bench_regime.mean()) * 252, 4
                        ),
                        "information_ratio": round(
                            (regime_returns.mean() - bench_regime.mean()) /
                            (regime_returns - bench_regime).std() * np.sqrt(252)
                            if (regime_returns - bench_regime).std() > 0 else 0,
                            2
                        ),
                    }

            results["by_regime"][regime] = regime_metrics

        # Add regime transition analysis
        results["transition_performance"] = self._analyze_transitions(
            strategy_returns, aligned_regimes
        )

        # Generate insights
        results["insights"] = self._generate_insights(results)

        return results

    def _compute_metrics(self, returns: pd.Series) -> dict[str, float]:
        """Compute performance metrics."""
        if len(returns) < 2:
            return {}

        return {
            "count_days": len(returns),
            "total_return": round((1 + returns).prod() - 1, 4),
            "mean_return_annual": round(returns.mean() * 252, 4),
            "volatility_annual": round(returns.std() * np.sqrt(252), 4),
            "sharpe_ratio": round(
                (returns.mean() / returns.std()) * np.sqrt(252)
                if returns.std() > 0 else 0,
                2
            ),
            "max_drawdown": round(self._compute_max_dd(returns), 4),
            "win_rate": round((returns > 0).mean(), 3),
            "best_day": round(returns.max(), 4),
            "worst_day": round(returns.min(), 4),
        }

    def _compute_max_dd(self, returns: pd.Series) -> float:
        """Compute maximum drawdown."""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()

    def _analyze_transitions(
        self,
        returns: pd.Series,
        regimes: pd.Series,
    ) -> dict[str, Any]:
        """Analyze performance around regime transitions."""
        transitions = []

        for i in range(1, len(regimes)):
            if regimes.iloc[i] != regimes.iloc[i-1]:
                if regimes.iloc[i-1] != RegimeType.UNKNOWN.value and \
                   regimes.iloc[i] != RegimeType.UNKNOWN.value:
                    transitions.append({
                        "date": regimes.index[i],
                        "from": regimes.iloc[i-1],
                        "to": regimes.iloc[i],
                    })

        if not transitions:
            return {"message": "No regime transitions detected"}

        # Analyze returns around transitions
        window = 5  # Days before/after transition
        transition_returns = []

        for t in transitions:
            idx = returns.index.get_indexer([t["date"]])[0]
            if idx >= window and idx < len(returns) - window:
                before = returns.iloc[idx-window:idx].mean()
                after = returns.iloc[idx:idx+window].mean()
                transition_returns.append({
                    "from": t["from"],
                    "to": t["to"],
                    "return_before": before * 252,
                    "return_after": after * 252,
                })

        if not transition_returns:
            return {"n_transitions": len(transitions)}

        # Aggregate by transition type
        by_transition = {}
        for tr in transition_returns:
            key = f"{tr['from']}_to_{tr['to']}"
            if key not in by_transition:
                by_transition[key] = {"before": [], "after": []}
            by_transition[key]["before"].append(tr["return_before"])
            by_transition[key]["after"].append(tr["return_after"])

        summary = {}
        for key, values in by_transition.items():
            summary[key] = {
                "count": len(values["before"]),
                "avg_return_before": round(np.mean(values["before"]), 4),
                "avg_return_after": round(np.mean(values["after"]), 4),
            }

        return {
            "n_transitions": len(transitions),
            "by_transition_type": summary,
        }

    def _generate_insights(self, results: dict) -> list[str]:
        """Generate insights from conditional analysis."""
        insights = []

        by_regime = results.get("by_regime", {})
        if not by_regime:
            return ["Insufficient data for regime-based insights"]

        # Find best/worst regimes
        sharpe_by_regime = {
            r: m.get("sharpe_ratio", 0)
            for r, m in by_regime.items()
        }

        if sharpe_by_regime:
            best_regime = max(sharpe_by_regime, key=sharpe_by_regime.get)
            worst_regime = min(sharpe_by_regime, key=sharpe_by_regime.get)

            insights.append(
                f"Strategy performs best in {best_regime} regime "
                f"(Sharpe: {sharpe_by_regime[best_regime]:.2f})"
            )

            if sharpe_by_regime[worst_regime] < 0:
                insights.append(
                    f"Warning: Strategy loses money in {worst_regime} regime "
                    f"(Sharpe: {sharpe_by_regime[worst_regime]:.2f})"
                )

        # Check consistency
        sharpe_values = list(sharpe_by_regime.values())
        if len(sharpe_values) >= 2:
            sharpe_std = np.std(sharpe_values)
            if sharpe_std > 0.5:
                insights.append(
                    "Strategy performance varies significantly by regime - "
                    "consider regime-specific parameters"
                )
            else:
                insights.append(
                    "Strategy shows consistent performance across regimes"
                )

        # Current regime insight
        current = results.get("regime_analysis", {}).get("current_regime")
        if current:
            regime = current.get("regime")
            if regime in by_regime:
                perf = by_regime[regime]
                insights.append(
                    f"Current regime is {regime} - "
                    f"historical Sharpe in this regime: {perf.get('sharpe_ratio', 0):.2f}"
                )

        return insights


# Convenience functions
def detect_regimes(
    data: pd.DataFrame,
    method: str = "rule_based",
    n_regimes: int = 3,
) -> dict[str, Any]:
    """
    Detect market regimes in price data.

    Args:
        data: OHLCV DataFrame
        method: Detection method ('rule_based' or 'hmm')
        n_regimes: Number of regimes for HMM

    Returns:
        Regime analysis results
    """
    if method == "hmm":
        if not HMM_AVAILABLE:
            return {"success": False, "error": "hmmlearn not installed"}
        detector = HMMRegimeDetector(n_regimes=n_regimes)
    else:
        detector = RuleBasedRegimeDetector()

    try:
        analysis = detector.detect(data)
        return {
            "success": True,
            "data": analysis.to_dict(),
        }
    except Exception as e:
        logger.error(f"Regime detection failed: {e}")
        return {"success": False, "error": str(e)}


def evaluate_by_regime(
    strategy_returns: pd.Series,
    market_data: pd.DataFrame,
    benchmark_returns: pd.Series | None = None,
) -> dict[str, Any]:
    """
    Evaluate strategy performance by market regime.

    Args:
        strategy_returns: Strategy returns
        market_data: Market OHLCV data
        benchmark_returns: Optional benchmark returns

    Returns:
        Conditional evaluation results
    """
    evaluator = ConditionalEvaluator()

    try:
        results = evaluator.evaluate(strategy_returns, market_data, benchmark_returns)
        return {"success": True, "data": results}
    except Exception as e:
        logger.error(f"Conditional evaluation failed: {e}")
        return {"success": False, "error": str(e)}


def get_current_regime(
    data: pd.DataFrame,
    method: str = "rule_based",
) -> dict[str, Any]:
    """
    Get current market regime.

    Args:
        data: Recent OHLCV data
        method: Detection method

    Returns:
        Current regime info
    """
    result = detect_regimes(data, method)

    if not result["success"]:
        return result

    current = result["data"].get("current_regime")
    if current:
        return {"success": True, "data": current}
    else:
        return {"success": False, "error": "Could not determine current regime"}
