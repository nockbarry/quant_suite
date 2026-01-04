"""
Daily Review Dashboard for Human Oversight.

Generates daily review documents summarizing research findings,
promotion candidates, and next priorities for human approval.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json


@dataclass
class NovelFinding:
    """Novel pattern finding for review."""
    priority: str  # high, medium, low
    description: str
    evidence: list[str]
    confidence: float
    actionable: bool
    source: str


@dataclass
class StrategyResult:
    """Strategy test result for review."""
    strategy: str
    symbol: str
    sharpe: float
    p_value: float
    pdt_hold_days: int
    production_ready: bool


@dataclass
class RegimeStatus:
    """Current regime status."""
    classification: str
    confidence: float
    recommended_strategies: list[str]
    avoid_strategies: list[str]


@dataclass
class PromotionCandidate:
    """Strategy candidate for promotion."""
    strategy: str
    symbol: str
    sharpe: float
    p_value: float
    hold_days: int
    target_pool: str  # budget or full


@dataclass
class DailyReview:
    """Complete daily review document."""
    date: datetime
    summary: dict
    novel_patterns: list[NovelFinding]
    strategy_results: list[StrategyResult]
    regime_assessment: RegimeStatus | None
    promotion_candidates: list[PromotionCandidate]
    recommended_priorities: list[dict]
    cross_track_patterns: list[dict]


@dataclass
class HumanDecisions:
    """Captured human decisions from review."""
    reviewed_at: datetime
    approved_promotions: list[dict]
    rejected_promotions: list[dict]
    accepted_priorities: list[str]
    custom_priorities: list[str]
    notes: str
    reviewer: str = "human"


class DailyReviewDashboard:
    """
    Generate daily review documents for human oversight.

    Compiles research findings, validates promotion candidates,
    and presents for human approval before any strategies go live.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or "/home/nock/quant_results/daily_reviews")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_review(
        self,
        novel_patterns: list[dict] | None = None,
        strategy_results: list[dict] | None = None,
        regime: dict | None = None,
        cross_track: list[dict] | None = None,
    ) -> DailyReview:
        """
        Generate a daily review document from research results.

        Args:
            novel_patterns: Findings from Track 1 (macro, news, regime)
            strategy_results: Results from Track 2 (strategy testing)
            regime: Current regime assessment
            cross_track: Cross-track pattern discoveries

        Returns:
            DailyReview document
        """
        # Parse novel patterns
        patterns = []
        for p in (novel_patterns or []):
            patterns.append(NovelFinding(
                priority=p.get("priority", "medium"),
                description=p.get("description", ""),
                evidence=p.get("evidence", []),
                confidence=p.get("confidence", 0.5),
                actionable=p.get("actionable", False),
                source=p.get("source", "unknown"),
            ))

        # Parse strategy results
        strategies = []
        for s in (strategy_results or []):
            strategies.append(StrategyResult(
                strategy=s.get("strategy", ""),
                symbol=s.get("symbol", ""),
                sharpe=s.get("sharpe", 0.0),
                p_value=s.get("p_value", 1.0),
                pdt_hold_days=s.get("pdt_hold_days", 0),
                production_ready=s.get("production_ready", False),
            ))

        # Parse regime
        regime_status = None
        if regime:
            regime_status = RegimeStatus(
                classification=regime.get("classification", "unknown"),
                confidence=regime.get("confidence", 0.0),
                recommended_strategies=regime.get("recommended_strategies", []),
                avoid_strategies=regime.get("avoid_strategies", []),
            )

        # Identify promotion candidates (production-ready strategies)
        candidates = []
        for s in strategies:
            if s.production_ready:
                candidates.append(PromotionCandidate(
                    strategy=s.strategy,
                    symbol=s.symbol,
                    sharpe=s.sharpe,
                    p_value=s.p_value,
                    hold_days=s.pdt_hold_days,
                    target_pool="budget" if s.pdt_hold_days >= 2 else "full",
                ))

        # Generate priorities
        priorities = self._generate_priorities(patterns, strategies, regime_status)

        # Build summary
        summary = {
            "research_cycles_completed": 1,
            "experiments_run": len(strategies),
            "significant_strategies": sum(1 for s in strategies if s.p_value < 0.05),
            "novel_patterns_found": len(patterns),
            "promotion_candidates": len(candidates),
        }

        return DailyReview(
            date=datetime.now(),
            summary=summary,
            novel_patterns=patterns,
            strategy_results=strategies,
            regime_assessment=regime_status,
            promotion_candidates=candidates,
            recommended_priorities=priorities,
            cross_track_patterns=cross_track or [],
        )

    def _generate_priorities(
        self,
        patterns: list[NovelFinding],
        strategies: list[StrategyResult],
        regime: RegimeStatus | None
    ) -> list[dict]:
        """Generate recommended next priorities."""
        priorities = []

        # Priority 1: Extend successful strategies
        successful = [s for s in strategies if s.p_value < 0.05 and s.sharpe > 1.5]
        if successful:
            best = max(successful, key=lambda x: x.sharpe)
            priorities.append({
                "description": f"Extend {best.strategy} testing to more symbols in same sector",
                "urgency": "high",
                "rationale": f"Strong results: Sharpe={best.sharpe:.2f}, p={best.p_value:.4f}",
            })

        # Priority 2: Regime-aligned strategies
        if regime and regime.recommended_strategies:
            priorities.append({
                "description": f"Test {', '.join(regime.recommended_strategies[:2])} (regime-aligned)",
                "urgency": "medium",
                "rationale": f"Current {regime.classification} regime (confidence: {regime.confidence:.0%})",
            })

        # Priority 3: Follow up on actionable patterns
        actionable = [p for p in patterns if p.actionable and p.confidence > 0.6]
        for p in actionable[:2]:
            priorities.append({
                "description": f"Investigate: {p.description[:50]}...",
                "urgency": "medium",
                "rationale": f"Actionable pattern (confidence: {p.confidence:.0%})",
            })

        return priorities

    def to_markdown(self, review: DailyReview) -> str:
        """Convert review to markdown for human reading."""
        lines = [
            "# Daily Research Review",
            "",
            f"**Date**: {review.date.strftime('%Y-%m-%d %H:%M')}",
            "",
            "---",
            "",
            "## Summary",
            "",
            f"- Research cycles completed: {review.summary.get('research_cycles_completed', 0)}",
            f"- Experiments run: {review.summary.get('experiments_run', 0)}",
            f"- Significant strategies found: {review.summary.get('significant_strategies', 0)}",
            f"- Novel patterns identified: {review.summary.get('novel_patterns_found', 0)}",
            "",
        ]

        # Regime Assessment
        if review.regime_assessment:
            r = review.regime_assessment
            lines.extend([
                "## Current Regime",
                "",
                f"- **Classification**: {r.classification}",
                f"- **Confidence**: {r.confidence:.0%}",
                f"- **Recommended strategies**: {', '.join(r.recommended_strategies[:3])}",
                f"- **Avoid strategies**: {', '.join(r.avoid_strategies[:3])}",
                "",
            ])

        # Novel Patterns
        if review.novel_patterns:
            lines.extend([
                "## Novel Pattern Findings",
                "",
            ])
            for i, p in enumerate(review.novel_patterns, 1):
                marker = "!!" if p.priority == "high" else ("!" if p.priority == "medium" else "")
                actionable = "(Actionable)" if p.actionable else ""
                lines.append(f"{i}. **[{p.priority.upper()}{marker}]** {p.description} {actionable}")
                if p.evidence:
                    lines.append(f"   - Evidence: {', '.join(p.evidence[:3])}")
                lines.append(f"   - Confidence: {p.confidence:.0%} | Source: {p.source}")
                lines.append("")

        # Strategy Results
        if review.strategy_results:
            lines.extend([
                "## Strategy Results",
                "",
                "| Strategy | Symbol | Sharpe | p-value | PDT Hold | Status |",
                "|----------|--------|--------|---------|----------|--------|",
            ])
            for s in sorted(review.strategy_results, key=lambda x: x.sharpe, reverse=True)[:10]:
                status = "**PROMOTE?**" if s.production_ready else ("Significant" if s.p_value < 0.05 else "-")
                lines.append(
                    f"| {s.strategy} | {s.symbol} | {s.sharpe:.2f} | {s.p_value:.4f} | {s.pdt_hold_days}d | {status} |"
                )
            lines.append("")

        # Cross-Track Patterns
        if review.cross_track_patterns:
            lines.extend([
                "## Cross-Track Patterns",
                "",
            ])
            for p in review.cross_track_patterns:
                lines.append(f"- {p.get('description', 'Pattern detected')}")
            lines.append("")

        # Promotion Candidates
        if review.promotion_candidates:
            lines.extend([
                "## Promotion Candidates (Require Approval)",
                "",
            ])
            for c in review.promotion_candidates:
                lines.append(
                    f"- [ ] **{c.strategy}/{c.symbol}** → {c.target_pool}_pool "
                    f"({c.hold_days}d hold, Sharpe={c.sharpe:.2f})"
                )
            lines.append("")

        # Priorities
        if review.recommended_priorities:
            lines.extend([
                "## Suggested Next Priorities",
                "",
            ])
            for i, p in enumerate(review.recommended_priorities, 1):
                lines.append(f"{i}. {p['description']} ({p['urgency']})")
                lines.append(f"   - *{p['rationale']}*")
            lines.append("")

        # Decision Section
        lines.extend([
            "---",
            "",
            "## Your Decisions Needed",
            "",
            "### Promotions",
            "Mark [x] next to strategies you approve for promotion.",
            "",
            "### Priorities",
            "- [ ] Accept suggested priorities",
            "- [ ] Modify priorities (specify below)",
            "",
            "### Custom Focus",
            "```",
            "Enter any custom research focus here...",
            "```",
            "",
            "### Notes",
            "```",
            "Any additional notes or concerns...",
            "```",
            "",
        ])

        return "\n".join(lines)

    def save_review(self, review: DailyReview, filename: str | None = None) -> Path:
        """Save review to file."""
        filename = filename or f"review_{review.date.strftime('%Y%m%d_%H%M%S')}.md"
        filepath = self.output_dir / filename

        markdown = self.to_markdown(review)
        with open(filepath, "w") as f:
            f.write(markdown)

        # Also save JSON version
        json_path = self.output_dir / filename.replace(".md", ".json")
        with open(json_path, "w") as f:
            json.dump(self._review_to_dict(review), f, indent=2, default=str)

        return filepath

    def _review_to_dict(self, review: DailyReview) -> dict:
        """Convert review to dictionary."""
        return {
            "date": review.date.isoformat(),
            "summary": review.summary,
            "novel_patterns": [
                {
                    "priority": p.priority,
                    "description": p.description,
                    "evidence": p.evidence,
                    "confidence": p.confidence,
                    "actionable": p.actionable,
                    "source": p.source,
                }
                for p in review.novel_patterns
            ],
            "strategy_results": [
                {
                    "strategy": s.strategy,
                    "symbol": s.symbol,
                    "sharpe": s.sharpe,
                    "p_value": s.p_value,
                    "pdt_hold_days": s.pdt_hold_days,
                    "production_ready": s.production_ready,
                }
                for s in review.strategy_results
            ],
            "regime": {
                "classification": review.regime_assessment.classification,
                "confidence": review.regime_assessment.confidence,
                "recommended": review.regime_assessment.recommended_strategies,
                "avoid": review.regime_assessment.avoid_strategies,
            } if review.regime_assessment else None,
            "promotion_candidates": [
                {
                    "strategy": c.strategy,
                    "symbol": c.symbol,
                    "sharpe": c.sharpe,
                    "p_value": c.p_value,
                    "hold_days": c.hold_days,
                    "target_pool": c.target_pool,
                }
                for c in review.promotion_candidates
            ],
            "priorities": review.recommended_priorities,
            "cross_track": review.cross_track_patterns,
        }

    def capture_decisions(
        self,
        approved: list[dict],
        rejected: list[dict],
        accept_priorities: bool,
        custom_priorities: list[str],
        notes: str,
    ) -> HumanDecisions:
        """
        Capture human decisions from review.

        Args:
            approved: List of approved promotions
            rejected: List of rejected promotions
            accept_priorities: Whether suggested priorities were accepted
            custom_priorities: Any custom priorities added
            notes: Additional notes from reviewer

        Returns:
            HumanDecisions record
        """
        decisions = HumanDecisions(
            reviewed_at=datetime.now(),
            approved_promotions=approved,
            rejected_promotions=rejected,
            accepted_priorities=["suggested"] if accept_priorities else [],
            custom_priorities=custom_priorities,
            notes=notes,
        )

        # Save decisions
        decisions_file = self.output_dir / f"decisions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(decisions_file, "w") as f:
            json.dump({
                "reviewed_at": decisions.reviewed_at.isoformat(),
                "approved_promotions": decisions.approved_promotions,
                "rejected_promotions": decisions.rejected_promotions,
                "accepted_priorities": decisions.accepted_priorities,
                "custom_priorities": decisions.custom_priorities,
                "notes": decisions.notes,
            }, f, indent=2)

        return decisions


# Convenience function
def generate_daily_review(
    novel_patterns: list[dict] | None = None,
    strategy_results: list[dict] | None = None,
    regime: dict | None = None,
    cross_track: list[dict] | None = None,
    save: bool = True,
) -> tuple[DailyReview, Path | None]:
    """
    Generate and optionally save a daily review.

    Returns tuple of (review, filepath if saved)
    """
    dashboard = DailyReviewDashboard()
    review = dashboard.generate_review(
        novel_patterns=novel_patterns,
        strategy_results=strategy_results,
        regime=regime,
        cross_track=cross_track,
    )

    filepath = None
    if save:
        filepath = dashboard.save_review(review)

    return review, filepath
