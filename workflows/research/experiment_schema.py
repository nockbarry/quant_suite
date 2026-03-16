"""
Experiment Documentation Standard.

Standardized experiment definition and documentation for reproducibility
and audit trail. As specified in Section 3.6.2 of the Testing Suite documentation.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))

logger = logging.getLogger(__name__)


class ExperimentStatus(str, Enum):
    """Status of an experiment."""
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SignificanceLevel(str, Enum):
    """Statistical significance level."""
    NOT_SIGNIFICANT = "not_significant"
    MARGINAL = "marginal"  # p < 0.10
    SIGNIFICANT = "significant"  # p < 0.05
    HIGHLY_SIGNIFICANT = "highly_significant"  # p < 0.01


@dataclass
class MethodologyConfig:
    """Methodology configuration for an experiment."""
    universe: str = "US_EQUITIES"
    features_tested: list[str] = field(default_factory=list)
    target: str = "forward_5d_return"
    test_type: str = "walk_forward"  # walk_forward, purged_cv, holdout
    train_period_days: int = 504  # 2 years
    test_period_days: int = 63  # 3 months
    embargo_days: int = 5
    statistical_tests: list[str] = field(default_factory=lambda: ["permutation_test", "bootstrap_ci"])
    n_permutations: int = 1000
    confidence_level: float = 0.95


@dataclass
class ResultsSummary:
    """Summary of experiment results."""
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    max_drawdown: float | None = None
    cagr: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    p_value: float | None = None
    significant: bool = False
    confidence_interval: tuple[float, float] | None = None
    edge_magnitude: str = ""  # Human-readable description
    oos_performance: dict[str, float] = field(default_factory=dict)


@dataclass
class ExperimentDefinition:
    """
    Standardized experiment definition for documentation and reproducibility.

    As specified in Section 3.6.2 of the Testing Suite documentation.
    """

    # Identification
    experiment_id: str
    title: str
    created_by: str  # 'research_agent_v2', 'human:name', etc.
    created_at: datetime
    status: ExperimentStatus = ExperimentStatus.PLANNED

    # Hypothesis - the most important part!
    hypothesis: str = ""  # What we're testing
    rationale: str = ""  # Why we think this might work
    expected_outcome: str = ""  # What success looks like

    # Methodology
    methodology: MethodologyConfig = field(default_factory=MethodologyConfig)

    # Code reference
    code_path: str | None = None  # Path to implementation
    commit_hash: str | None = None  # Git commit

    # Results (filled after running)
    results: ResultsSummary = field(default_factory=ResultsSummary)
    visualizations: list[str] = field(default_factory=list)  # Paths to charts

    # Analysis
    conclusions: str = ""
    learnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    # Relationships
    related_experiments: list[str] = field(default_factory=list)
    parent_experiment: str | None = None  # If this is a variation
    child_experiments: list[str] = field(default_factory=list)

    # Metadata
    tags: list[str] = field(default_factory=list)
    priority: int = 5  # 1 (highest) to 10 (lowest)
    estimated_runtime_minutes: int | None = None
    actual_runtime_minutes: int | None = None

    # Versioning
    version: int = 1
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["status"] = self.status.value
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperimentDefinition":
        """Create from dictionary."""
        # Convert datetime strings
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        # Convert status
        if isinstance(data.get("status"), str):
            data["status"] = ExperimentStatus(data["status"])
        # Convert nested objects
        if isinstance(data.get("methodology"), dict):
            data["methodology"] = MethodologyConfig(**data["methodology"])
        if isinstance(data.get("results"), dict):
            data["results"] = ResultsSummary(**data["results"])
        return cls(**data)

    def to_yaml(self) -> str:
        """Export to YAML format for human-readable documentation."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "ExperimentDefinition":
        """Load from YAML string."""
        data = yaml.safe_load(yaml_str)
        return cls.from_dict(data)

    def generate_id(self) -> str:
        """Generate a unique experiment ID."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        content_hash = hashlib.md5(
            f"{self.title}{self.hypothesis}".encode()
        ).hexdigest()[:6]
        return f"EXP-{timestamp}-{content_hash}"

    def validate(self) -> list[str]:
        """Validate experiment definition."""
        errors = []

        if not self.experiment_id:
            errors.append("experiment_id is required")
        if not self.title:
            errors.append("title is required")
        if not self.hypothesis:
            errors.append("hypothesis is required - what are we testing?")
        if not self.methodology.features_tested:
            errors.append("methodology.features_tested should list features being tested")

        return errors


class ExperimentRegistry:
    """
    Registry for managing experiments.

    Provides persistence, querying, and relationship management.
    """

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else _RESULTS_DIR / "experiments"
        self.path.mkdir(parents=True, exist_ok=True)
        self._experiments: dict[str, ExperimentDefinition] = {}
        self._load()

    def _load(self) -> None:
        """Load all experiments from disk."""
        for file_path in self.path.glob("*.yaml"):
            try:
                content = file_path.read_text()
                exp = ExperimentDefinition.from_yaml(content)
                self._experiments[exp.experiment_id] = exp
            except Exception as e:
                logger.warning(f"Failed to load {file_path}: {e}")

    def _save_experiment(self, exp: ExperimentDefinition) -> None:
        """Save single experiment to disk."""
        file_path = self.path / f"{exp.experiment_id}.yaml"
        file_path.write_text(exp.to_yaml())

    def create(
        self,
        title: str,
        hypothesis: str,
        created_by: str = "system",
        **kwargs,
    ) -> ExperimentDefinition:
        """
        Create a new experiment.

        Args:
            title: Experiment title
            hypothesis: What we're testing
            created_by: Author
            **kwargs: Additional fields

        Returns:
            Created experiment
        """
        exp = ExperimentDefinition(
            experiment_id="",
            title=title,
            hypothesis=hypothesis,
            created_by=created_by,
            created_at=datetime.now(),
            **kwargs,
        )
        exp.experiment_id = exp.generate_id()

        # Validate
        errors = exp.validate()
        if errors:
            raise ValueError(f"Invalid experiment: {errors}")

        self._experiments[exp.experiment_id] = exp
        self._save_experiment(exp)
        return exp

    def get(self, experiment_id: str) -> ExperimentDefinition | None:
        """Get experiment by ID."""
        return self._experiments.get(experiment_id)

    def update(self, exp: ExperimentDefinition) -> None:
        """Update an existing experiment."""
        if exp.experiment_id not in self._experiments:
            raise ValueError(f"Experiment {exp.experiment_id} not found")

        exp.version += 1
        exp.updated_at = datetime.now()
        self._experiments[exp.experiment_id] = exp
        self._save_experiment(exp)

    def mark_running(self, experiment_id: str) -> None:
        """Mark experiment as running."""
        exp = self.get(experiment_id)
        if exp:
            exp.status = ExperimentStatus.RUNNING
            self.update(exp)

    def mark_completed(
        self,
        experiment_id: str,
        results: ResultsSummary,
        conclusions: str = "",
        learnings: list[str] | None = None,
        next_steps: list[str] | None = None,
    ) -> None:
        """Mark experiment as completed with results."""
        exp = self.get(experiment_id)
        if exp:
            exp.status = ExperimentStatus.COMPLETED
            exp.results = results
            exp.conclusions = conclusions
            exp.learnings = learnings or []
            exp.next_steps = next_steps or []
            self.update(exp)

    def mark_failed(self, experiment_id: str, reason: str) -> None:
        """Mark experiment as failed."""
        exp = self.get(experiment_id)
        if exp:
            exp.status = ExperimentStatus.FAILED
            exp.conclusions = f"FAILED: {reason}"
            self.update(exp)

    def query(
        self,
        status: ExperimentStatus | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
        significant_only: bool = False,
        min_sharpe: float | None = None,
        date_range: tuple[datetime, datetime] | None = None,
    ) -> list[ExperimentDefinition]:
        """
        Query experiments with filters.

        Args:
            status: Filter by status
            tags: Filter by tags (any match)
            created_by: Filter by creator
            significant_only: Only return significant results
            min_sharpe: Minimum Sharpe ratio
            date_range: (start, end) date range

        Returns:
            Matching experiments
        """
        results = list(self._experiments.values())

        if status:
            results = [e for e in results if e.status == status]
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        if created_by:
            results = [e for e in results if e.created_by == created_by]
        if significant_only:
            results = [e for e in results if e.results.significant]
        if min_sharpe is not None:
            results = [e for e in results if e.results.sharpe_ratio and e.results.sharpe_ratio >= min_sharpe]
        if date_range:
            start, end = date_range
            results = [e for e in results if start <= e.created_at <= end]

        return sorted(results, key=lambda e: e.created_at, reverse=True)

    def get_failed_hypotheses(
        self,
        category: str | None = None,
    ) -> list[ExperimentDefinition]:
        """
        Get failed experiments to learn from.

        Important for avoiding repeated mistakes!
        """
        failed = self.query(status=ExperimentStatus.FAILED)
        if category:
            failed = [e for e in failed if category.lower() in e.title.lower()]
        return failed

    def get_successful(
        self,
        min_sharpe: float = 0.5,
    ) -> list[ExperimentDefinition]:
        """Get successful experiments."""
        return [
            e for e in self._experiments.values()
            if e.status == ExperimentStatus.COMPLETED
            and e.results.significant
            and e.results.sharpe_ratio
            and e.results.sharpe_ratio >= min_sharpe
        ]

    def suggest_next_experiments(self, n: int = 5) -> list[dict[str, Any]]:
        """
        Suggest promising next experiments based on past results.

        Returns experiment ideas with rationale.
        """
        suggestions = []

        # 1. Variations of successful experiments
        for exp in self.get_successful()[:3]:
            if len(suggestions) >= n:
                break
            suggestions.append({
                "type": "variation",
                "parent": exp.experiment_id,
                "title": f"Variation of {exp.title}",
                "rationale": f"Parent had Sharpe={exp.results.sharpe_ratio:.2f}",
                "suggestion": "Try different parameters or features",
            })

        # 2. Combine successful approaches
        successful = self.get_successful()
        if len(successful) >= 2:
            exp1, exp2 = successful[:2]
            suggestions.append({
                "type": "combination",
                "parents": [exp1.experiment_id, exp2.experiment_id],
                "title": f"Combine {exp1.title} + {exp2.title}",
                "rationale": "Both approaches worked individually",
                "suggestion": "Ensemble or feature combination",
            })

        # 3. Unexplored areas from failed experiments
        for exp in self.get_failed_hypotheses()[:2]:
            if len(suggestions) >= n:
                break
            if exp.next_steps:
                suggestions.append({
                    "type": "retry_with_modification",
                    "parent": exp.experiment_id,
                    "title": f"Revised: {exp.title}",
                    "rationale": f"Previous attempt failed: {exp.conclusions[:100]}",
                    "suggestion": exp.next_steps[0] if exp.next_steps else "Try different approach",
                })

        return suggestions[:n]

    def summary(self) -> dict[str, Any]:
        """Get registry summary."""
        by_status = {}
        for exp in self._experiments.values():
            status = exp.status.value
            by_status[status] = by_status.get(status, 0) + 1

        successful = self.get_successful()
        failed = self.query(status=ExperimentStatus.FAILED)

        return {
            "total_experiments": len(self._experiments),
            "by_status": by_status,
            "successful_count": len(successful),
            "success_rate": len(successful) / len(self._experiments) if self._experiments else 0,
            "avg_sharpe_successful": (
                sum(e.results.sharpe_ratio for e in successful if e.results.sharpe_ratio) / len(successful)
                if successful else 0
            ),
            "common_failure_reasons": self._analyze_failures(failed),
        }

    def _analyze_failures(self, failed: list[ExperimentDefinition]) -> list[str]:
        """Analyze common failure patterns."""
        reasons = {}
        for exp in failed:
            # Simple keyword extraction from conclusions
            conclusion = exp.conclusions.lower()
            if "overfit" in conclusion:
                reasons["overfitting"] = reasons.get("overfitting", 0) + 1
            elif "not significant" in conclusion:
                reasons["not_significant"] = reasons.get("not_significant", 0) + 1
            elif "data quality" in conclusion:
                reasons["data_quality"] = reasons.get("data_quality", 0) + 1
            else:
                reasons["other"] = reasons.get("other", 0) + 1

        return sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3]


# =============================================================================
# EXPERIMENT TEMPLATES
# =============================================================================

def create_momentum_experiment(
    lookback_period: int = 252,
    skip_recent: int = 21,
    universe: str = "SP500",
    created_by: str = "system",
) -> ExperimentDefinition:
    """Create a template for momentum experiments."""
    return ExperimentDefinition(
        experiment_id="",
        title=f"Cross-sectional Momentum ({lookback_period}-{skip_recent})",
        hypothesis=(
            f"Stocks with highest {lookback_period}-day momentum (excluding last {skip_recent} days) "
            "will outperform in the next month due to behavioral biases and slow information diffusion."
        ),
        rationale="Jegadeesh-Titman momentum effect is well-documented across markets and time periods.",
        expected_outcome="Long-short portfolio Sharpe > 0.5, p-value < 0.05",
        created_by=created_by,
        created_at=datetime.now(),
        methodology=MethodologyConfig(
            universe=universe,
            features_tested=[f"momentum_{lookback_period}d", f"momentum_{skip_recent}d", "volatility_21d"],
            target="forward_21d_return",
            test_type="walk_forward",
            train_period_days=504,
            test_period_days=63,
        ),
        tags=["momentum", "factor", "well-known"],
    )


def create_sentiment_experiment(
    sentiment_source: str = "reddit",
    sentiment_type: str = "contrarian",
    created_by: str = "system",
) -> ExperimentDefinition:
    """Create a template for sentiment experiments."""
    return ExperimentDefinition(
        experiment_id="",
        title=f"{sentiment_type.title()} {sentiment_source.title()} Sentiment",
        hypothesis=(
            f"Extreme {'positive' if sentiment_type == 'contrarian' else 'negative'} sentiment on {sentiment_source} "
            f"is a {'sell' if sentiment_type == 'contrarian' else 'buy'} signal for retail-favorite stocks."
        ),
        rationale="Retail sentiment extremes often precede mean reversion in meme stocks.",
        expected_outcome="Strategy Sharpe > 0.8, alpha significant at 5% level",
        created_by=created_by,
        created_at=datetime.now(),
        methodology=MethodologyConfig(
            universe="RETAIL_FAVORITES",
            features_tested=[
                f"{sentiment_source}_sentiment_7d_ma",
                f"{sentiment_source}_volume_zscore",
                f"{sentiment_source}_sentiment_momentum_3d",
            ],
            target="forward_5d_return",
            test_type="walk_forward",
            train_period_days=252,
            test_period_days=42,
        ),
        tags=["sentiment", "alternative_data", sentiment_source, sentiment_type],
    )


def create_alternative_data_experiment(
    data_source: str,
    signal_name: str,
    created_by: str = "system",
) -> ExperimentDefinition:
    """Create a template for alternative data experiments."""
    return ExperimentDefinition(
        experiment_id="",
        title=f"Alternative Data: {data_source} - {signal_name}",
        hypothesis=(
            f"{signal_name} derived from {data_source} contains alpha "
            "not yet priced into stocks."
        ),
        rationale=f"Novel data source {data_source} may provide informational edge.",
        expected_outcome="Information coefficient > 0.02, statistically significant",
        created_by=created_by,
        created_at=datetime.now(),
        methodology=MethodologyConfig(
            features_tested=[signal_name],
            target="forward_5d_return",
            test_type="walk_forward",
        ),
        tags=["alternative_data", data_source, "novel"],
    )
