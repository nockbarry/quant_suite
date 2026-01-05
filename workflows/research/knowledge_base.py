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


@dataclass
class DataSourceAlpha:
    """Track which data sources provide edge."""
    source: str  # e.g., 'semianalysis', 'fred_gold', 'dram_prices'
    source_type: str  # 'blog', 'api', 'scrape', 'etf_proxy'
    predictions_made: int = 0
    predictions_correct: int = 0
    cumulative_alpha: float = 0.0  # Total alpha generated
    best_strategy: str = ""  # Strategy that worked best with this source
    best_sharpe: float = 0.0
    symbols_affected: list[str] = field(default_factory=list)
    first_used: str = ""
    last_used: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "DataSourceAlpha":
        return cls(**d)

    @property
    def hit_rate(self) -> float:
        """Prediction accuracy."""
        if self.predictions_made == 0:
            return 0.0
        return self.predictions_correct / self.predictions_made

    @property
    def alpha_per_prediction(self) -> float:
        """Average alpha per prediction."""
        if self.predictions_made == 0:
            return 0.0
        return self.cumulative_alpha / self.predictions_made

    @property
    def is_valuable(self) -> bool:
        """Source is considered valuable if hit rate > 55% and has 5+ predictions."""
        return self.predictions_made >= 5 and self.hit_rate > 0.55


@dataclass
class CausalRelationship:
    """Discovered cause → effect relationship."""
    id: str
    cause: str  # e.g., 'dram_prices', 'fed_rate', 'vix'
    effect: str  # e.g., 'semiconductor_stocks', 'tech_sector', 'MU'
    lag_days: int  # How many days before effect manifests
    correlation: float  # Pearson correlation
    p_value: float  # Statistical significance
    mechanism: str  # Explanation of why this relationship exists
    discovered_at: str
    verified_count: int = 0  # Times this relationship was verified
    last_verified: str = ""
    confidence: float = 0.5  # 0-1, increases with verification
    regime_dependent: bool = False  # True if only works in certain regimes
    regime_notes: str = ""  # Which regimes it works in

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CausalRelationship":
        return cls(**d)

    @property
    def is_significant(self) -> bool:
        """Relationship is statistically significant."""
        return self.p_value < 0.05

    @property
    def is_strong(self) -> bool:
        """Strong correlation with high confidence."""
        return abs(self.correlation) > 0.3 and self.confidence > 0.7


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
        self._data_sources_file = self.path / "data_sources.json"
        self._causal_relationships_file = self.path / "causal_relationships.json"

        # In-memory storage
        self.insights: list[Insight] = []
        self.successes: list[StrategyResult] = []
        self.failures: list[dict] = []
        self.patterns: list[Pattern] = []
        self.data_quality: dict[str, dict] = {}
        self.tested_hypotheses: set[str] = set()
        self.data_sources: dict[str, DataSourceAlpha] = {}
        self.causal_relationships: list[CausalRelationship] = []

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

        # Load data sources
        if self._data_sources_file.exists():
            data = json.loads(self._data_sources_file.read_text())
            self.data_sources = {
                k: DataSourceAlpha.from_dict(v)
                for k, v in data.get("sources", {}).items()
            }

        # Load causal relationships
        if self._causal_relationships_file.exists():
            data = json.loads(self._causal_relationships_file.read_text())
            self.causal_relationships = [
                CausalRelationship.from_dict(d)
                for d in data.get("relationships", [])
            ]

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

        # Save data sources
        self._data_sources_file.write_text(json.dumps({
            "sources": {k: v.to_dict() for k, v in self.data_sources.items()},
            "updated_at": datetime.now().isoformat(),
        }, indent=2))

        # Save causal relationships
        self._causal_relationships_file.write_text(json.dumps({
            "relationships": [r.to_dict() for r in self.causal_relationships],
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
    # DATA SOURCE ALPHA TRACKING
    # =========================================================================

    def record_data_source_performance(
        self,
        source: str,
        source_type: str,
        prediction_correct: bool,
        alpha_generated: float = 0.0,
        strategy_name: str = "",
        sharpe: float = 0.0,
        symbols: list[str] | None = None,
        notes: str = "",
    ) -> DataSourceAlpha:
        """
        Record a prediction outcome for a data source.

        This allows the system to learn which data sources provide real edge.

        Args:
            source: Data source identifier (e.g., 'semianalysis', 'fred_gold')
            source_type: Type of source ('blog', 'api', 'scrape', 'etf_proxy')
            prediction_correct: Whether the prediction was correct
            alpha_generated: Alpha generated by this prediction (in decimal)
            strategy_name: Strategy that used this source
            sharpe: Sharpe ratio achieved
            symbols: Symbols affected by this source
            notes: Additional notes

        Returns:
            Updated DataSourceAlpha record
        """
        now = datetime.now().isoformat()

        if source not in self.data_sources:
            self.data_sources[source] = DataSourceAlpha(
                source=source,
                source_type=source_type,
                predictions_made=0,
                predictions_correct=0,
                cumulative_alpha=0.0,
                best_strategy="",
                best_sharpe=0.0,
                symbols_affected=[],
                first_used=now,
                last_used=now,
                notes=notes,
            )

        ds = self.data_sources[source]
        ds.predictions_made += 1
        ds.last_used = now

        if prediction_correct:
            ds.predictions_correct += 1

        ds.cumulative_alpha += alpha_generated

        if sharpe > ds.best_sharpe:
            ds.best_sharpe = sharpe
            ds.best_strategy = strategy_name

        if symbols:
            for sym in symbols:
                if sym not in ds.symbols_affected:
                    ds.symbols_affected.append(sym)

        if notes and notes not in ds.notes:
            ds.notes = f"{ds.notes}; {notes}" if ds.notes else notes

        self._save()
        return ds

    def get_best_data_sources(
        self,
        min_predictions: int = 3,
        sort_by: str = "hit_rate",  # 'hit_rate', 'alpha', 'sharpe'
    ) -> list[DataSourceAlpha]:
        """
        Get data sources ranked by their edge.

        Args:
            min_predictions: Minimum predictions to be included
            sort_by: Sorting criterion

        Returns:
            List of DataSourceAlpha sorted by performance
        """
        sources = [
            ds for ds in self.data_sources.values()
            if ds.predictions_made >= min_predictions
        ]

        if sort_by == "hit_rate":
            sources.sort(key=lambda x: x.hit_rate, reverse=True)
        elif sort_by == "alpha":
            sources.sort(key=lambda x: x.cumulative_alpha, reverse=True)
        elif sort_by == "sharpe":
            sources.sort(key=lambda x: x.best_sharpe, reverse=True)

        return sources

    def get_valuable_data_sources(self) -> list[DataSourceAlpha]:
        """Get data sources that have proven valuable (>55% hit rate, 5+ predictions)."""
        return [ds for ds in self.data_sources.values() if ds.is_valuable]

    def get_data_source(self, source: str) -> DataSourceAlpha | None:
        """Get a specific data source record."""
        return self.data_sources.get(source)

    def get_data_source_summary(self) -> dict:
        """Get summary of all data source performance."""
        if not self.data_sources:
            return {
                "total_sources": 0,
                "valuable_sources": [],
                "total_predictions": 0,
                "overall_hit_rate": 0.0,
            }

        total_predictions = sum(ds.predictions_made for ds in self.data_sources.values())
        total_correct = sum(ds.predictions_correct for ds in self.data_sources.values())

        return {
            "total_sources": len(self.data_sources),
            "valuable_sources": [ds.source for ds in self.get_valuable_data_sources()],
            "total_predictions": total_predictions,
            "overall_hit_rate": total_correct / total_predictions if total_predictions > 0 else 0.0,
            "top_by_hit_rate": [
                {"source": ds.source, "hit_rate": ds.hit_rate}
                for ds in self.get_best_data_sources(min_predictions=3, sort_by="hit_rate")[:5]
            ],
            "top_by_alpha": [
                {"source": ds.source, "alpha": ds.cumulative_alpha}
                for ds in self.get_best_data_sources(min_predictions=3, sort_by="alpha")[:5]
            ],
        }

    # =========================================================================
    # CAUSAL RELATIONSHIP TRACKING
    # =========================================================================

    def record_causal_relationship(
        self,
        cause: str,
        effect: str,
        lag_days: int,
        correlation: float,
        p_value: float,
        mechanism: str = "",
        regime_dependent: bool = False,
        regime_notes: str = "",
    ) -> CausalRelationship:
        """
        Record a discovered causal relationship.

        Args:
            cause: The leading indicator (e.g., 'dram_prices', 'fed_rate')
            effect: What it affects (e.g., 'semiconductor_stocks', 'MU')
            lag_days: How many days the effect lags the cause
            correlation: Pearson correlation coefficient
            p_value: Statistical significance
            mechanism: Explanation of why this relationship exists
            regime_dependent: Whether it only works in certain regimes
            regime_notes: Details about which regimes

        Returns:
            The created or updated CausalRelationship
        """
        now = datetime.now().isoformat()

        # Check if relationship already exists
        existing = self._find_causal_relationship(cause, effect)

        if existing:
            # Update existing relationship
            existing.correlation = correlation
            existing.p_value = p_value
            existing.lag_days = lag_days
            existing.verified_count += 1
            existing.last_verified = now
            existing.confidence = min(0.95, existing.confidence + 0.1)
            if mechanism and mechanism != existing.mechanism:
                existing.mechanism = mechanism
            if regime_dependent != existing.regime_dependent:
                existing.regime_dependent = regime_dependent
            if regime_notes:
                existing.regime_notes = regime_notes
            self._save()
            return existing

        # Create new relationship
        relationship = CausalRelationship(
            id=f"causal_{len(self.causal_relationships):04d}",
            cause=cause,
            effect=effect,
            lag_days=lag_days,
            correlation=correlation,
            p_value=p_value,
            mechanism=mechanism,
            discovered_at=now,
            verified_count=1,
            last_verified=now,
            confidence=0.5 if p_value >= 0.05 else 0.7,
            regime_dependent=regime_dependent,
            regime_notes=regime_notes,
        )
        self.causal_relationships.append(relationship)
        self._save()
        return relationship

    def _find_causal_relationship(
        self, cause: str, effect: str
    ) -> CausalRelationship | None:
        """Find an existing causal relationship."""
        for rel in self.causal_relationships:
            if rel.cause == cause and rel.effect == effect:
                return rel
        return None

    def get_causal_chain(self, target: str) -> list[CausalRelationship]:
        """
        Get all causal relationships that affect a target.

        Args:
            target: The effect to search for (e.g., 'MU', 'semiconductor_stocks')

        Returns:
            List of relationships where target is the effect, sorted by correlation
        """
        relationships = [
            rel for rel in self.causal_relationships
            if rel.effect == target or target in rel.effect
        ]
        return sorted(relationships, key=lambda x: abs(x.correlation), reverse=True)

    def get_leading_indicators(self, effect: str) -> list[dict]:
        """
        Get leading indicators for a given effect.

        Returns list of dicts with cause, lag, correlation, and confidence.
        """
        chain = self.get_causal_chain(effect)
        return [
            {
                "cause": rel.cause,
                "lag_days": rel.lag_days,
                "correlation": rel.correlation,
                "p_value": rel.p_value,
                "confidence": rel.confidence,
                "mechanism": rel.mechanism,
                "is_significant": rel.is_significant,
            }
            for rel in chain
        ]

    def get_effects_of(self, cause: str) -> list[CausalRelationship]:
        """
        Get all effects caused by a given indicator.

        Args:
            cause: The leading indicator to search for

        Returns:
            List of relationships where cause matches
        """
        return [
            rel for rel in self.causal_relationships
            if rel.cause == cause or cause in rel.cause
        ]

    def get_significant_relationships(
        self,
        min_confidence: float = 0.6,
    ) -> list[CausalRelationship]:
        """Get statistically significant relationships with high confidence."""
        return [
            rel for rel in self.causal_relationships
            if rel.is_significant and rel.confidence >= min_confidence
        ]

    def get_strong_relationships(self) -> list[CausalRelationship]:
        """Get relationships with strong correlation and high confidence."""
        return [rel for rel in self.causal_relationships if rel.is_strong]

    def get_causal_summary(self) -> dict:
        """Get summary of all causal relationships."""
        if not self.causal_relationships:
            return {
                "total_relationships": 0,
                "significant_relationships": 0,
                "strong_relationships": 0,
                "unique_causes": [],
                "unique_effects": [],
            }

        return {
            "total_relationships": len(self.causal_relationships),
            "significant_relationships": len(
                [r for r in self.causal_relationships if r.is_significant]
            ),
            "strong_relationships": len(self.get_strong_relationships()),
            "unique_causes": list(set(r.cause for r in self.causal_relationships)),
            "unique_effects": list(set(r.effect for r in self.causal_relationships)),
            "avg_lag_days": sum(r.lag_days for r in self.causal_relationships)
            / len(self.causal_relationships),
            "top_correlations": [
                {
                    "cause": r.cause,
                    "effect": r.effect,
                    "correlation": r.correlation,
                    "lag_days": r.lag_days,
                }
                for r in sorted(
                    self.causal_relationships,
                    key=lambda x: abs(x.correlation),
                    reverse=True,
                )[:5]
            ],
        }

    def suggest_research_from_relationships(self) -> list[dict]:
        """
        Suggest research based on discovered causal relationships.

        Returns research ideas based on:
        1. Verified relationships that could inform strategies
        2. Relationships that need more verification
        3. Potential transitive relationships (A→B, B→C implies A→C?)
        """
        suggestions = []

        # Suggest strategies based on strong relationships
        for rel in self.get_strong_relationships():
            suggestions.append({
                "type": "strategy_idea",
                "priority": 0.9,
                "idea": f"Build strategy using {rel.cause} to predict {rel.effect}",
                "details": f"Lag: {rel.lag_days} days, Correlation: {rel.correlation:.2f}",
                "relationship_id": rel.id,
            })

        # Suggest verification for promising but unverified relationships
        for rel in self.causal_relationships:
            if rel.is_significant and rel.verified_count < 3:
                suggestions.append({
                    "type": "verification",
                    "priority": 0.7,
                    "idea": f"Verify {rel.cause} → {rel.effect} relationship",
                    "details": f"Only verified {rel.verified_count} time(s)",
                    "relationship_id": rel.id,
                })

        # Look for transitive relationships
        effects_dict = {}
        for rel in self.causal_relationships:
            if rel.effect not in effects_dict:
                effects_dict[rel.effect] = []
            effects_dict[rel.effect].append(rel)

        for rel in self.causal_relationships:
            # If A causes B, and B causes C, suggest testing A → C
            if rel.effect in effects_dict:
                for downstream in effects_dict.get(rel.cause, []):
                    if not self._find_causal_relationship(rel.cause, downstream.effect):
                        suggestions.append({
                            "type": "transitive_test",
                            "priority": 0.6,
                            "idea": f"Test if {rel.cause} → {downstream.effect} (transitive)",
                            "details": f"Via: {rel.cause} → {rel.effect} → {downstream.effect}",
                            "combined_lag": rel.lag_days + downstream.lag_days,
                        })

        return sorted(suggestions, key=lambda x: x["priority"], reverse=True)

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
            # Data source alpha tracking
            "total_data_sources": len(self.data_sources),
            "valuable_data_sources": [ds.source for ds in self.get_valuable_data_sources()],
            "data_source_hit_rate": (
                sum(ds.predictions_correct for ds in self.data_sources.values())
                / max(1, sum(ds.predictions_made for ds in self.data_sources.values()))
            ),
            # Causal relationship tracking
            "total_causal_relationships": len(self.causal_relationships),
            "significant_relationships": len(self.get_significant_relationships()),
            "strong_relationships": len(self.get_strong_relationships()),
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

        # Recommend valuable data sources
        for ds in self.get_valuable_data_sources()[:3]:
            recs.append(
                f"Use data source '{ds.source}' ({ds.hit_rate:.1%} hit rate, "
                f"{ds.cumulative_alpha:.2%} cumulative alpha)"
            )

        # Recommend exploiting strong causal relationships
        for rel in self.get_strong_relationships()[:3]:
            recs.append(
                f"Exploit relationship: {rel.cause} → {rel.effect} "
                f"(lag={rel.lag_days}d, r={rel.correlation:.2f})"
            )

        return recs
