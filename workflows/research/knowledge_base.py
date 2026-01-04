"""
Persistent knowledge base for autonomous research.

Stores learnings across sessions:
- Successful strategies and their patterns
- Failed hypotheses (avoid re-testing)
- Data quality observations
- Accumulated insights
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


@dataclass
class Insight:
    """A learned insight from research."""
    id: str
    timestamp: str
    category: Literal["strategy", "data", "symbol", "pattern", "warning"]
    content: str
    evidence: list[str] = field(default_factory=list)  # Session IDs
    confidence: float = 0.5  # 0-1
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Insight":
        return cls(**d)


@dataclass
class StrategyResult:
    """Record of a strategy test result."""
    strategy_name: str
    symbol: str
    params: dict
    train_sharpe: float
    val_sharpe: float
    p_value: float
    is_significant: bool
    session_id: str
    timestamp: str
    validation_period: str  # "3m" or "6m"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyResult":
        return cls(**d)


@dataclass
class Pattern:
    """A detected pattern from research."""
    id: str
    name: str
    description: str
    symbols: list[str]
    strategies: list[str]
    avg_p_value: float
    n_successes: int
    confidence: float
    discovered_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Pattern":
        return cls(**d)


class KnowledgeBase:
    """
    Persistent storage for research insights and learnings.

    Accumulates knowledge across sessions to improve hypothesis generation.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or Path.home() / "quant_results" / "knowledge"
        self.path.mkdir(parents=True, exist_ok=True)

        # Storage files
        self._insights_file = self.path / "insights.json"
        self._successes_file = self.path / "successful_strategies.json"
        self._failures_file = self.path / "failed_hypotheses.json"
        self._patterns_file = self.path / "patterns.json"
        self._data_quality_file = self.path / "data_quality.json"
        self._tested_file = self.path / "tested_hypotheses.json"

        # In-memory storage
        self.insights: list[Insight] = []
        self.successes: list[StrategyResult] = []
        self.failures: list[dict] = []
        self.patterns: list[Pattern] = []
        self.data_quality: dict[str, dict] = {}
        self.tested_hypotheses: set[str] = set()

        self._load()

    def _load(self) -> None:
        """Load all knowledge from disk."""
        # Load insights
        if self._insights_file.exists():
            data = json.loads(self._insights_file.read_text())
            self.insights = [Insight.from_dict(d) for d in data.get("insights", [])]

        # Load successes
        if self._successes_file.exists():
            data = json.loads(self._successes_file.read_text())
            self.successes = [StrategyResult.from_dict(d) for d in data.get("results", [])]

        # Load failures
        if self._failures_file.exists():
            data = json.loads(self._failures_file.read_text())
            self.failures = data.get("failures", [])

        # Load patterns
        if self._patterns_file.exists():
            data = json.loads(self._patterns_file.read_text())
            self.patterns = [Pattern.from_dict(d) for d in data.get("patterns", [])]

        # Load data quality
        if self._data_quality_file.exists():
            self.data_quality = json.loads(self._data_quality_file.read_text())

        # Load tested hypotheses
        if self._tested_file.exists():
            data = json.loads(self._tested_file.read_text())
            self.tested_hypotheses = set(data.get("tested", []))

    def _save(self) -> None:
        """Save all knowledge to disk."""
        # Save insights
        self._insights_file.write_text(json.dumps({
            "insights": [i.to_dict() for i in self.insights],
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

        # Save successes
        self._successes_file.write_text(json.dumps({
            "results": [s.to_dict() for s in self.successes],
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

        # Save failures
        self._failures_file.write_text(json.dumps({
            "failures": self.failures,
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

        # Save patterns
        self._patterns_file.write_text(json.dumps({
            "patterns": [p.to_dict() for p in self.patterns],
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

        # Save data quality
        self._data_quality_file.write_text(json.dumps(self.data_quality, indent=2))

        # Save tested hypotheses
        self._tested_file.write_text(json.dumps({
            "tested": list(self.tested_hypotheses),
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

    # =========================================================================
    # INSIGHTS MANAGEMENT
    # =========================================================================

    def add_insight(
        self,
        category: str,
        content: str,
        evidence: list[str] = None,
        confidence: float = 0.5,
        tags: list[str] = None,
    ) -> Insight:
        """Add a new insight."""
        insight = Insight(
            id=f"ins_{len(self.insights):04d}",
            timestamp=datetime.now().isoformat(),
            category=category,
            content=content,
            evidence=evidence or [],
            confidence=confidence,
            tags=tags or [],
        )
        self.insights.append(insight)
        self._save()
        return insight

    def get_insights(
        self,
        category: str = None,
        min_confidence: float = 0.0,
    ) -> list[Insight]:
        """Get insights, optionally filtered."""
        results = self.insights
        if category:
            results = [i for i in results if i.category == category]
        if min_confidence > 0:
            results = [i for i in results if i.confidence >= min_confidence]
        return sorted(results, key=lambda x: x.confidence, reverse=True)

    # =========================================================================
    # STRATEGY TRACKING
    # =========================================================================

    def record_success(
        self,
        strategy_name: str,
        symbol: str,
        params: dict,
        train_sharpe: float,
        val_sharpe: float,
        p_value: float,
        session_id: str,
        validation_period: str = "6m",
    ) -> None:
        """Record a successful (significant) strategy result."""
        result = StrategyResult(
            strategy_name=strategy_name,
            symbol=symbol,
            params=params,
            train_sharpe=train_sharpe,
            val_sharpe=val_sharpe,
            p_value=p_value,
            is_significant=True,
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            validation_period=validation_period,
        )
        self.successes.append(result)
        self._save()

        # Update patterns
        self._update_patterns(result)

    def record_failure(
        self,
        strategy_name: str,
        symbol: str,
        params: dict,
        reason: str,
        session_id: str,
    ) -> None:
        """Record a failed hypothesis."""
        self.failures.append({
            "strategy_name": strategy_name,
            "symbol": symbol,
            "params": params,
            "reason": reason,
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def get_successful_strategies(
        self,
        symbol: str = None,
        min_sharpe: float = 0.0,
    ) -> list[StrategyResult]:
        """Get successful strategies, optionally filtered."""
        results = self.successes
        if symbol:
            results = [r for r in results if r.symbol == symbol]
        if min_sharpe > 0:
            results = [r for r in results if r.val_sharpe >= min_sharpe]
        return sorted(results, key=lambda x: x.val_sharpe, reverse=True)

    def get_winning_strategy_names(self) -> list[str]:
        """Get unique strategy names that have succeeded."""
        return list(set(r.strategy_name for r in self.successes))

    def get_winning_symbols(self) -> list[str]:
        """Get symbols where strategies have succeeded."""
        return list(set(r.symbol for r in self.successes))

    # =========================================================================
    # PATTERN DETECTION
    # =========================================================================

    def _update_patterns(self, result: StrategyResult) -> None:
        """Update patterns based on new success."""
        # Check for existing pattern
        for pattern in self.patterns:
            if result.strategy_name in pattern.strategies:
                if result.symbol not in pattern.symbols:
                    pattern.symbols.append(result.symbol)
                pattern.n_successes += 1
                pattern.avg_p_value = (
                    (pattern.avg_p_value * (pattern.n_successes - 1) + result.p_value)
                    / pattern.n_successes
                )
                pattern.confidence = min(0.95, pattern.confidence + 0.05)
                return

        # Create new pattern if strategy has multiple successes
        strategy_successes = [s for s in self.successes if s.strategy_name == result.strategy_name]
        if len(strategy_successes) >= 2:
            symbols = list(set(s.symbol for s in strategy_successes))
            p_values = [s.p_value for s in strategy_successes]
            self.patterns.append(Pattern(
                id=f"pat_{len(self.patterns):04d}",
                name=f"{result.strategy_name}_works",
                description=f"{result.strategy_name} shows significance on multiple symbols",
                symbols=symbols,
                strategies=[result.strategy_name],
                avg_p_value=sum(p_values) / len(p_values),
                n_successes=len(strategy_successes),
                confidence=0.6,
                discovered_at=datetime.now().isoformat(),
            ))

    def get_patterns(self, min_confidence: float = 0.0) -> list[Pattern]:
        """Get detected patterns."""
        results = self.patterns
        if min_confidence > 0:
            results = [p for p in results if p.confidence >= min_confidence]
        return sorted(results, key=lambda x: x.confidence, reverse=True)

    # =========================================================================
    # DATA QUALITY TRACKING
    # =========================================================================

    def log_data_quality(
        self,
        source: str,
        symbol: str,
        quality: float,
        notes: str = "",
    ) -> None:
        """Log data quality observation."""
        key = f"{source}_{symbol}"
        if key not in self.data_quality:
            self.data_quality[key] = {
                "source": source,
                "symbol": symbol,
                "observations": [],
            }
        self.data_quality[key]["observations"].append({
            "quality": quality,
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 10 observations
        self.data_quality[key]["observations"] = self.data_quality[key]["observations"][-10:]
        self._save()

    def get_data_quality(self, source: str = None, symbol: str = None) -> dict:
        """Get data quality observations."""
        results = {}
        for key, value in self.data_quality.items():
            if source and value["source"] != source:
                continue
            if symbol and value["symbol"] != symbol:
                continue
            # Calculate average quality
            obs = value["observations"]
            if obs:
                avg_quality = sum(o["quality"] for o in obs) / len(obs)
                results[key] = {
                    **value,
                    "avg_quality": avg_quality,
                }
        return results

    def get_reliable_sources(self, min_quality: float = 0.7) -> list[str]:
        """Get sources with good data quality."""
        quality_by_source: dict[str, list[float]] = {}
        for value in self.data_quality.values():
            source = value["source"]
            if source not in quality_by_source:
                quality_by_source[source] = []
            for obs in value["observations"]:
                quality_by_source[source].append(obs["quality"])

        reliable = []
        for source, qualities in quality_by_source.items():
            if qualities and sum(qualities) / len(qualities) >= min_quality:
                reliable.append(source)
        return reliable

    # =========================================================================
    # HYPOTHESIS TRACKING
    # =========================================================================

    def _hypothesis_hash(self, strategy: str, symbol: str, params: dict) -> str:
        """Generate unique hash for hypothesis."""
        key = f"{strategy}_{symbol}_{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def was_tested(self, strategy: str, symbol: str, params: dict) -> bool:
        """Check if hypothesis was already tested."""
        h = self._hypothesis_hash(strategy, symbol, params)
        return h in self.tested_hypotheses

    def mark_tested(self, strategy: str, symbol: str, params: dict) -> None:
        """Mark hypothesis as tested."""
        h = self._hypothesis_hash(strategy, symbol, params)
        self.tested_hypotheses.add(h)
        self._save()

    def get_untested_combinations(
        self,
        strategies: list[str],
        symbols: list[str],
    ) -> list[tuple[str, str]]:
        """Get strategy-symbol combinations not yet tested."""
        untested = []
        for strategy in strategies:
            for symbol in symbols:
                if not self.was_tested(strategy, symbol, {}):
                    untested.append((strategy, symbol))
        return untested

    # =========================================================================
    # DEDUPLICATION AND EXPERIMENT CHECKING
    # =========================================================================

    def check_before_experiment(
        self,
        strategy: str,
        symbol: str,
        params: dict | None = None,
    ) -> dict:
        """
        Check if experiment was already run or is too similar.

        Call this BEFORE running any experiment to avoid duplicate work.

        Args:
            strategy: Strategy name
            symbol: Symbol to test
            params: Optional parameter dict

        Returns:
            Dictionary with:
            - already_tested: Whether exact experiment was run
            - similar_experiments: List of similar past experiments
            - recommendation: 'skip', 'run', or 'run_with_variation'
            - reason: Explanation for recommendation
        """
        params = params or {}

        # Check exact match
        already_tested = self.was_tested(strategy, symbol, params)

        # Find similar experiments
        similar = self.find_similar_experiments(strategy, symbol, params)

        # Determine recommendation
        if already_tested:
            recommendation = "skip"
            reason = "Exact experiment already tested"
        elif similar:
            # Check if similar experiments succeeded
            successful_similar = [s for s in similar if s.get("was_successful", False)]
            if successful_similar:
                recommendation = "run_with_variation"
                reason = f"Similar successful experiment exists. Try different params."
            else:
                recommendation = "run"
                reason = "Similar experiments failed, but params differ enough"
        else:
            recommendation = "run"
            reason = "New experiment, not previously tested"

        return {
            "already_tested": already_tested,
            "similar_experiments": similar,
            "recommendation": recommendation,
            "reason": reason,
        }

    def find_similar_experiments(
        self,
        strategy: str,
        symbol: str,
        params: dict | None = None,
        threshold: float = 0.8,
    ) -> list[dict]:
        """
        Find experiments similar to the proposed one.

        Args:
            strategy: Strategy name
            symbol: Symbol
            params: Parameters
            threshold: Similarity threshold (0-1)

        Returns:
            List of similar past experiments
        """
        similar = []
        params = params or {}

        # Check successes
        for success in self.successes:
            if success.strategy_name == strategy and success.symbol == symbol:
                similarity = self._param_similarity(params, success.params)
                if similarity >= threshold:
                    similar.append({
                        "type": "success",
                        "strategy": success.strategy_name,
                        "symbol": success.symbol,
                        "params": success.params,
                        "sharpe": success.val_sharpe,
                        "p_value": success.p_value,
                        "similarity": similarity,
                        "was_successful": True,
                    })

        # Check failures
        for failure in self.failures:
            if failure["strategy_name"] == strategy and failure["symbol"] == symbol:
                failure_params = failure.get("params", {})
                similarity = self._param_similarity(params, failure_params)
                if similarity >= threshold:
                    similar.append({
                        "type": "failure",
                        "strategy": failure["strategy_name"],
                        "symbol": failure["symbol"],
                        "params": failure_params,
                        "reason": failure.get("reason", ""),
                        "similarity": similarity,
                        "was_successful": False,
                    })

        return sorted(similar, key=lambda x: x["similarity"], reverse=True)

    def _param_similarity(self, params1: dict, params2: dict) -> float:
        """
        Compute similarity between two parameter dicts.

        Returns 1.0 for identical, 0.0 for completely different.
        """
        if not params1 and not params2:
            return 1.0

        if not params1 or not params2:
            return 0.0

        all_keys = set(params1.keys()) | set(params2.keys())
        if not all_keys:
            return 1.0

        matches = 0
        for key in all_keys:
            v1 = params1.get(key)
            v2 = params2.get(key)

            if v1 == v2:
                matches += 1
            elif isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
                # Numeric values: partial credit for close values
                if v1 != 0 and v2 != 0:
                    ratio = min(v1, v2) / max(v1, v2)
                    matches += ratio

        return matches / len(all_keys)

    def get_promising_variations(self, n: int = 10) -> list[dict]:
        """
        Suggest parameter variations of successful strategies.

        Returns experiments worth trying based on what's worked.
        """
        variations = []

        # Group successes by strategy
        by_strategy = {}
        for success in self.successes:
            if success.strategy_name not in by_strategy:
                by_strategy[success.strategy_name] = []
            by_strategy[success.strategy_name].append(success)

        for strategy, successes in by_strategy.items():
            if len(successes) < 2:
                continue

            # Find symbols where this strategy hasn't been tested
            tested_symbols = {s.symbol for s in successes}

            # Common symbols to try
            common_symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "AMD", "TSLA", "META", "AMZN"]
            untested = [s for s in common_symbols if s not in tested_symbols]

            # Get best performing params
            best = max(successes, key=lambda x: x.val_sharpe)

            for symbol in untested[:3]:
                # Check we haven't already tested with these params
                if not self.was_tested(strategy, symbol, best.params):
                    variations.append({
                        "strategy": strategy,
                        "symbol": symbol,
                        "suggested_params": best.params,
                        "reason": f"Best params from {best.symbol} (Sharpe={best.val_sharpe:.2f})",
                        "expected_sharpe": best.val_sharpe,
                    })

        # Sort by expected sharpe
        variations = sorted(variations, key=lambda x: x["expected_sharpe"], reverse=True)
        return variations[:n]

    def summarize_failures(self) -> dict:
        """
        Summarize what has failed to help avoid repeating mistakes.

        Returns summary of failed hypotheses by strategy and symbol.
        """
        by_strategy = {}
        by_symbol = {}
        common_reasons = {}

        for failure in self.failures:
            strategy = failure["strategy_name"]
            symbol = failure["symbol"]
            reason = failure.get("reason", "Unknown")

            # Count by strategy
            if strategy not in by_strategy:
                by_strategy[strategy] = {"count": 0, "symbols": []}
            by_strategy[strategy]["count"] += 1
            if symbol not in by_strategy[strategy]["symbols"]:
                by_strategy[strategy]["symbols"].append(symbol)

            # Count by symbol
            if symbol not in by_symbol:
                by_symbol[symbol] = {"count": 0, "strategies": []}
            by_symbol[symbol]["count"] += 1
            if strategy not in by_symbol[symbol]["strategies"]:
                by_symbol[symbol]["strategies"].append(strategy)

            # Count reasons
            if reason not in common_reasons:
                common_reasons[reason] = 0
            common_reasons[reason] += 1

        # Find consistently failing strategies/symbols
        failing_strategies = [
            s for s, data in by_strategy.items()
            if data["count"] >= 3 and len(data["symbols"]) >= 2
        ]

        failing_symbols = [
            s for s, data in by_symbol.items()
            if data["count"] >= 3 and len(data["strategies"]) >= 2
        ]

        return {
            "total_failures": len(self.failures),
            "by_strategy": by_strategy,
            "by_symbol": by_symbol,
            "common_reasons": dict(sorted(
                common_reasons.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]),
            "avoid_strategies": failing_strategies,
            "difficult_symbols": failing_symbols,
        }

    # =========================================================================
    # SUMMARY AND STATS
    # =========================================================================

    def summary(self) -> dict[str, Any]:
        """Get summary of knowledge base."""
        return {
            "total_insights": len(self.insights),
            "total_successes": len(self.successes),
            "total_failures": len(self.failures),
            "total_patterns": len(self.patterns),
            "tested_hypotheses": len(self.tested_hypotheses),
            "winning_strategies": self.get_winning_strategy_names(),
            "winning_symbols": self.get_winning_symbols(),
            "high_confidence_patterns": [
                p.name for p in self.get_patterns(min_confidence=0.7)
            ],
        }

    def get_recommendations(self) -> list[str]:
        """Get recommendations based on accumulated knowledge."""
        recs = []

        # Recommend successful strategy-symbol combinations
        for result in self.successes[:5]:
            recs.append(
                f"Try {result.strategy_name} on {result.symbol} "
                f"(p={result.p_value:.3f}, Sharpe={result.val_sharpe:.2f})"
            )

        # Recommend patterns
        for pattern in self.get_patterns(min_confidence=0.7)[:3]:
            recs.append(
                f"Pattern: {pattern.name} - works on {pattern.symbols}"
            )

        # Warn about poor data sources
        for source in set(v["source"] for v in self.data_quality.values()):
            quality = self.get_data_quality(source=source)
            if quality:
                avg = sum(q["avg_quality"] for q in quality.values()) / len(quality)
                if avg < 0.5:
                    recs.append(f"Warning: {source} has low data quality ({avg:.1%})")

        return recs
