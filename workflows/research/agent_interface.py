"""
Agent Research Interface.

Interface for agents to interact with research documentation and knowledge base.
As specified in Section 3.6.3 of the Testing Suite documentation.

Provides:
- Query past experiments
- Learn from failures
- Get feature performance
- Suggest next experiments
- Document new findings
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from .knowledge_base import KnowledgeBase, Insight, StrategyResult, Pattern
from .experiment_schema import (
    ExperimentDefinition,
    ExperimentRegistry,
    ExperimentStatus,
    ResultsSummary,
    MethodologyConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class ExperimentProposal:
    """A proposed experiment with rationale."""
    title: str
    hypothesis: str
    rationale: str
    priority: int  # 1 (highest) to 10 (lowest)
    estimated_runtime_minutes: int
    features_to_test: list[str]
    suggested_methodology: MethodologyConfig
    parent_experiment: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class FeatureStats:
    """Statistics about a feature's historical performance."""
    feature_name: str
    avg_predictive_power: float  # Average IC or similar metric
    n_experiments_tested: int
    successful_experiments: int
    best_sharpe_achieved: float | None
    best_experiment_id: str | None
    correlation_with_returns: float | None
    stability_score: float  # How consistent is the signal
    recommended: bool
    notes: str = ""


@dataclass
class ResearchSummary:
    """Summary of research state for an agent."""
    total_experiments: int
    successful_experiments: int
    success_rate: float
    top_strategies: list[str]
    failing_areas: list[str]
    untested_opportunities: list[str]
    recent_discoveries: list[str]
    suggested_next_steps: list[str]


class ResearchKnowledgeBase:
    """
    Interface for agents to interact with research documentation.

    As specified in Section 3.6.3 of the Testing Suite documentation.
    """

    def __init__(
        self,
        kb_path: Path | str | None = None,
        exp_path: Path | str | None = None,
    ):
        """
        Initialize research knowledge base interface.

        Args:
            kb_path: Path to KnowledgeBase storage
            exp_path: Path to ExperimentRegistry storage
        """
        self.kb = KnowledgeBase(Path(kb_path) if kb_path else None)
        self.experiments = ExperimentRegistry(Path(exp_path) if exp_path else None)

        # Cache for feature performance
        self._feature_cache: dict[str, FeatureStats] = {}

    # =========================================================================
    # EXPERIMENT QUERIES
    # =========================================================================

    def query_experiments(
        self,
        filters: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        date_range: tuple[datetime, datetime] | None = None,
        min_sharpe: float | None = None,
        status: ExperimentStatus | None = None,
        limit: int = 20,
    ) -> list[ExperimentDefinition]:
        """
        Search past experiments.

        Args:
            filters: Additional filters (key-value pairs)
            tags: Filter by tags (any match)
            date_range: (start, end) date range
            min_sharpe: Minimum Sharpe ratio for results
            status: Filter by experiment status
            limit: Maximum results to return

        Returns:
            List of matching experiments
        """
        results = self.experiments.query(
            status=status,
            tags=tags,
            significant_only=(min_sharpe is not None),
            min_sharpe=min_sharpe,
            date_range=date_range,
        )

        # Apply additional filters
        if filters:
            for key, value in filters.items():
                results = [
                    e for e in results
                    if getattr(e, key, None) == value or
                    (hasattr(e.methodology, key) and getattr(e.methodology, key) == value)
                ]

        return results[:limit]

    def get_failed_hypotheses(
        self,
        category: str | None = None,
        limit: int = 20,
    ) -> list[ExperimentDefinition]:
        """
        Learn from what didn't work.

        Important for avoiding repeated mistakes!

        Args:
            category: Filter by category (e.g., 'momentum', 'sentiment')
            limit: Maximum results

        Returns:
            List of failed experiments with learnings
        """
        failed = self.experiments.get_failed_hypotheses(category)
        return failed[:limit]

    def get_similar_experiments(
        self,
        hypothesis: str,
        threshold: float = 0.5,
    ) -> list[ExperimentDefinition]:
        """
        Find experiments similar to a proposed hypothesis.

        Useful for checking if something has already been tried.

        Args:
            hypothesis: Proposed hypothesis text
            threshold: Similarity threshold

        Returns:
            Similar experiments
        """
        # Simple keyword matching (can be enhanced with embeddings)
        keywords = set(hypothesis.lower().split())
        scored = []

        for exp in self.experiments._experiments.values():
            exp_keywords = set(exp.hypothesis.lower().split())
            overlap = len(keywords & exp_keywords)
            similarity = overlap / len(keywords) if keywords else 0

            if similarity >= threshold:
                scored.append((exp, similarity))

        return [exp for exp, _ in sorted(scored, key=lambda x: x[1], reverse=True)]

    # =========================================================================
    # FEATURE ANALYSIS
    # =========================================================================

    def get_feature_performance(self, feature_name: str) -> FeatureStats:
        """
        Get historical predictive power of a feature.

        Args:
            feature_name: Name of the feature

        Returns:
            FeatureStats with performance metrics
        """
        if feature_name in self._feature_cache:
            return self._feature_cache[feature_name]

        # Scan experiments for this feature
        experiments_with_feature = []
        for exp in self.experiments._experiments.values():
            if feature_name in exp.methodology.features_tested:
                experiments_with_feature.append(exp)

        if not experiments_with_feature:
            stats = FeatureStats(
                feature_name=feature_name,
                avg_predictive_power=0.0,
                n_experiments_tested=0,
                successful_experiments=0,
                best_sharpe_achieved=None,
                best_experiment_id=None,
                correlation_with_returns=None,
                stability_score=0.0,
                recommended=False,
                notes="No experiments found with this feature",
            )
            self._feature_cache[feature_name] = stats
            return stats

        # Calculate statistics
        successful = [
            e for e in experiments_with_feature
            if e.status == ExperimentStatus.COMPLETED and e.results.significant
        ]

        sharpes = [
            e.results.sharpe_ratio
            for e in successful
            if e.results.sharpe_ratio is not None
        ]

        best_sharpe = max(sharpes) if sharpes else None
        best_exp = None
        if best_sharpe:
            best_exp = next(
                (e.experiment_id for e in successful if e.results.sharpe_ratio == best_sharpe),
                None
            )

        # Calculate stability (std of sharpes across experiments)
        stability = 1.0 - (np.std(sharpes) / np.mean(sharpes)) if sharpes and len(sharpes) > 1 else 0.5

        stats = FeatureStats(
            feature_name=feature_name,
            avg_predictive_power=np.mean(sharpes) if sharpes else 0.0,
            n_experiments_tested=len(experiments_with_feature),
            successful_experiments=len(successful),
            best_sharpe_achieved=best_sharpe,
            best_experiment_id=best_exp,
            correlation_with_returns=None,  # Would need actual return data
            stability_score=stability,
            recommended=len(successful) >= 2 and (best_sharpe or 0) > 0.5,
        )

        self._feature_cache[feature_name] = stats
        return stats

    def get_top_features(self, n: int = 10) -> list[FeatureStats]:
        """Get top performing features across all experiments."""
        # Collect all features
        all_features = set()
        for exp in self.experiments._experiments.values():
            all_features.update(exp.methodology.features_tested)

        # Score each feature
        stats = [self.get_feature_performance(f) for f in all_features]

        # Sort by average predictive power
        return sorted(
            stats,
            key=lambda s: (s.successful_experiments, s.avg_predictive_power),
            reverse=True,
        )[:n]

    # =========================================================================
    # NEXT STEPS SUGGESTIONS
    # =========================================================================

    def suggest_next_experiments(self, n: int = 5) -> list[ExperimentProposal]:
        """
        Based on past results, suggest promising research directions.

        Returns:
            List of experiment proposals with rationale
        """
        proposals = []

        # 1. High-performing feature variations
        top_features = self.get_top_features(5)
        for feature_stat in top_features:
            if feature_stat.recommended:
                proposals.append(ExperimentProposal(
                    title=f"Feature Variation: {feature_stat.feature_name}",
                    hypothesis=f"Variations of {feature_stat.feature_name} may improve performance",
                    rationale=f"Feature has {feature_stat.successful_experiments} successful experiments",
                    priority=3,
                    estimated_runtime_minutes=30,
                    features_to_test=[feature_stat.feature_name],
                    suggested_methodology=MethodologyConfig(
                        features_tested=[feature_stat.feature_name],
                    ),
                    tags=["feature_variation", "follow_up"],
                ))

        # 2. Unexplored combinations
        successful_exps = self.experiments.get_successful()
        if len(successful_exps) >= 2:
            exp1, exp2 = successful_exps[:2]
            combined_features = list(set(
                exp1.methodology.features_tested + exp2.methodology.features_tested
            ))

            proposals.append(ExperimentProposal(
                title=f"Ensemble: {exp1.title[:30]} + {exp2.title[:30]}",
                hypothesis="Combining successful strategies may improve risk-adjusted returns",
                rationale=f"Both strategies individually achieved Sharpe > 0.5",
                priority=2,
                estimated_runtime_minutes=60,
                features_to_test=combined_features,
                suggested_methodology=MethodologyConfig(
                    features_tested=combined_features,
                ),
                tags=["ensemble", "combination"],
            ))

        # 3. Retry failed experiments with modifications
        failed = self.get_failed_hypotheses(limit=5)
        for exp in failed[:2]:
            if exp.next_steps:
                proposals.append(ExperimentProposal(
                    title=f"Retry: {exp.title}",
                    hypothesis=exp.hypothesis,
                    rationale=f"Previous attempt failed. Suggested modification: {exp.next_steps[0]}",
                    priority=5,
                    estimated_runtime_minutes=45,
                    features_to_test=exp.methodology.features_tested,
                    suggested_methodology=exp.methodology,
                    parent_experiment=exp.experiment_id,
                    tags=["retry", "modified"],
                ))

        # 4. KB-based suggestions (patterns that worked)
        for pattern in self.kb.get_patterns(min_confidence=0.7)[:3]:
            proposals.append(ExperimentProposal(
                title=f"Pattern Extension: {pattern.name}",
                hypothesis=f"Extend pattern '{pattern.name}' to new symbols",
                rationale=f"Pattern has {pattern.n_successes} successes across {len(pattern.symbols)} symbols",
                priority=3,
                estimated_runtime_minutes=30,
                features_to_test=pattern.strategies,
                suggested_methodology=MethodologyConfig(),
                tags=["pattern_extension"],
            ))

        return sorted(proposals, key=lambda p: p.priority)[:n]

    # =========================================================================
    # DOCUMENTATION
    # =========================================================================

    def document_experiment(
        self,
        title: str,
        hypothesis: str,
        methodology: MethodologyConfig,
        author: str = "research_agent",
        tags: list[str] | None = None,
    ) -> ExperimentDefinition:
        """
        Create and save a new experiment.

        Args:
            title: Experiment title
            hypothesis: What we're testing
            methodology: How we're testing it
            author: Who created this
            tags: Tags for categorization

        Returns:
            Created experiment
        """
        exp = self.experiments.create(
            title=title,
            hypothesis=hypothesis,
            created_by=author,
            methodology=methodology,
            tags=tags or [],
        )
        logger.info(f"Documented experiment: {exp.experiment_id}")
        return exp

    def record_experiment_results(
        self,
        experiment_id: str,
        results: ResultsSummary,
        conclusions: str,
        learnings: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> None:
        """
        Record results of a completed experiment.

        Args:
            experiment_id: ID of the experiment
            results: Results summary
            conclusions: What we learned
            learnings: Key learnings
            next_steps: Suggested follow-ups
        """
        self.experiments.mark_completed(
            experiment_id=experiment_id,
            results=results,
            conclusions=conclusions,
            learnings=learnings,
            next_steps=next_steps,
        )

        # Also record in knowledge base
        exp = self.experiments.get(experiment_id)
        if exp and results.significant:
            for feature in exp.methodology.features_tested:
                self.kb.record_success(
                    strategy_name=exp.title,
                    symbol="UNIVERSE",  # Multi-symbol
                    params={"features": exp.methodology.features_tested},
                    train_sharpe=results.sharpe_ratio or 0,
                    val_sharpe=results.sharpe_ratio or 0,
                    p_value=results.p_value or 1.0,
                    session_id=experiment_id,
                )

        logger.info(f"Recorded results for: {experiment_id}")

    def add_insight(
        self,
        category: Literal["strategy", "data", "symbol", "pattern", "warning"],
        content: str,
        evidence: list[str] | None = None,
        confidence: float = 0.5,
        tags: list[str] | None = None,
    ) -> Insight:
        """
        Add a learned insight to the knowledge base.

        Args:
            category: Type of insight
            content: What we learned
            evidence: Supporting evidence (experiment IDs, etc.)
            confidence: How confident we are (0-1)
            tags: Tags for categorization

        Returns:
            Created insight
        """
        return self.kb.add_insight(
            category=category,
            content=content,
            evidence=evidence,
            confidence=confidence,
            tags=tags,
        )

    # =========================================================================
    # SUMMARY
    # =========================================================================

    def get_research_summary(self) -> ResearchSummary:
        """
        Get comprehensive summary of research state.

        Useful for agents to understand current progress.
        """
        exp_summary = self.experiments.summary()
        kb_summary = self.kb.summary()

        # Get top strategies
        successful = self.experiments.get_successful()
        top_strategies = [e.title for e in successful[:5]]

        # Get failing areas
        failure_summary = self.kb.summarize_failures()
        failing_areas = failure_summary.get("avoid_strategies", [])

        # Get untested opportunities
        variations = self.kb.get_promising_variations(n=5)
        untested = [v["strategy"] for v in variations]

        # Recent discoveries (last 30 days)
        recent_date = datetime.now() - timedelta(days=30)
        recent = [
            e.title for e in self.experiments._experiments.values()
            if e.created_at >= recent_date and e.results.significant
        ]

        # Suggested next steps
        suggestions = self.suggest_next_experiments(5)
        next_steps = [s.title for s in suggestions]

        return ResearchSummary(
            total_experiments=exp_summary["total_experiments"],
            successful_experiments=exp_summary["successful_count"],
            success_rate=exp_summary["success_rate"],
            top_strategies=top_strategies,
            failing_areas=failing_areas,
            untested_opportunities=untested,
            recent_discoveries=recent,
            suggested_next_steps=next_steps,
        )

    def should_try_experiment(
        self,
        hypothesis: str,
        features: list[str],
    ) -> dict[str, Any]:
        """
        Check if an experiment is worth trying.

        Args:
            hypothesis: Proposed hypothesis
            features: Features to test

        Returns:
            Recommendation with reasoning
        """
        # Check for similar experiments
        similar = self.get_similar_experiments(hypothesis, threshold=0.6)

        if similar:
            successful_similar = [e for e in similar if e.results.significant]
            if successful_similar:
                return {
                    "recommendation": "modify",
                    "reason": f"Similar successful experiment exists: {successful_similar[0].title}",
                    "suggestion": "Try with different parameters or features",
                    "similar_experiments": [e.experiment_id for e in similar[:3]],
                }
            else:
                failed_similar = [e for e in similar if e.status == ExperimentStatus.FAILED]
                if failed_similar:
                    return {
                        "recommendation": "caution",
                        "reason": f"Similar experiment failed: {failed_similar[0].title}",
                        "suggestion": failed_similar[0].conclusions[:200] if failed_similar[0].conclusions else "Review failure reason",
                        "similar_experiments": [e.experiment_id for e in similar[:3]],
                    }

        # Check feature performance
        feature_stats = [self.get_feature_performance(f) for f in features]
        good_features = [s for s in feature_stats if s.recommended]

        if good_features:
            return {
                "recommendation": "proceed",
                "reason": f"Features have good track record: {[f.feature_name for f in good_features]}",
                "suggestion": "Proceed with experiment",
                "expected_success_rate": len(good_features) / len(features),
            }

        return {
            "recommendation": "exploratory",
            "reason": "Novel experiment with untested features",
            "suggestion": "Proceed with caution, document thoroughly",
            "expected_success_rate": 0.2,  # Base rate
        }


# Import numpy for calculations
try:
    import numpy as np
except ImportError:
    # Fallback for environments without numpy
    class np:
        @staticmethod
        def mean(x): return sum(x) / len(x) if x else 0
        @staticmethod
        def std(x):
            if not x or len(x) < 2: return 0
            m = sum(x) / len(x)
            return (sum((i - m) ** 2 for i in x) / len(x)) ** 0.5
