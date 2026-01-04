"""
Result Aggregator for Multi-Agent Research Workflows.

Combines results from parallel agents, identifies patterns, and produces
consolidated reports for human review.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json
import re
from pathlib import Path

from .parallel_executor import AgentResult, AgentType, TaskStatus


class FindingPriority(Enum):
    """Priority level for findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class StrategyFinding:
    """A strategy finding from research."""
    strategy: str
    symbol: str
    sharpe: float
    p_value: float
    pdt_hold_days: int
    source_agent: str
    timestamp: datetime
    additional_metrics: dict = field(default_factory=dict)

    @property
    def is_significant(self) -> bool:
        return self.p_value < 0.05

    @property
    def is_production_ready(self) -> bool:
        return self.is_significant and self.sharpe > 0.5 and self.pdt_hold_days >= 2

    @property
    def priority(self) -> FindingPriority:
        if self.p_value < 0.01 and self.sharpe > 2.0:
            return FindingPriority.CRITICAL
        if self.p_value < 0.05 and self.sharpe > 1.5:
            return FindingPriority.HIGH
        if self.p_value < 0.05:
            return FindingPriority.MEDIUM
        return FindingPriority.LOW


@dataclass
class NovelPattern:
    """A novel pattern finding from macro/news research."""
    pattern_type: str  # e.g., "macro_correlation", "event_impact", "regime_signal"
    description: str
    evidence: list[str]
    confidence: float
    actionable: bool
    recommended_strategy: str | None
    source_agent: str
    timestamp: datetime

    @property
    def priority(self) -> FindingPriority:
        if self.confidence > 0.8 and self.actionable:
            return FindingPriority.CRITICAL
        if self.confidence > 0.6 and self.actionable:
            return FindingPriority.HIGH
        if self.confidence > 0.4:
            return FindingPriority.MEDIUM
        return FindingPriority.LOW


@dataclass
class RegimeAssessment:
    """Current market regime assessment."""
    regime: str  # e.g., "risk_on", "risk_off", "range_bound", "trending"
    confidence: float
    recommended_strategies: list[str]
    avoid_strategies: list[str]
    key_indicators: dict[str, float]
    timestamp: datetime


@dataclass
class ConsolidatedReport:
    """Consolidated report from all agent results."""
    cycle_id: str
    started_at: datetime
    completed_at: datetime
    focus: str

    # Track 1: Novel Patterns
    novel_patterns: list[NovelPattern]
    regime_assessment: RegimeAssessment | None

    # Track 2: Strategy Results
    strategy_findings: list[StrategyFinding]

    # Cross-track insights
    cross_track_patterns: list[dict]

    # Promotion candidates
    promotion_candidates: list[StrategyFinding]

    # Research leads for next cycle
    next_leads: list[dict]

    # Agent execution stats
    agents_executed: int
    agents_succeeded: int
    total_duration_seconds: float

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "focus": self.focus,
            "novel_patterns": [
                {
                    "type": p.pattern_type,
                    "description": p.description,
                    "evidence": p.evidence,
                    "confidence": p.confidence,
                    "actionable": p.actionable,
                    "priority": p.priority.value,
                }
                for p in self.novel_patterns
            ],
            "regime": {
                "classification": self.regime_assessment.regime if self.regime_assessment else None,
                "confidence": self.regime_assessment.confidence if self.regime_assessment else None,
                "recommended_strategies": self.regime_assessment.recommended_strategies if self.regime_assessment else [],
            } if self.regime_assessment else None,
            "strategy_findings": [
                {
                    "strategy": f.strategy,
                    "symbol": f.symbol,
                    "sharpe": f.sharpe,
                    "p_value": f.p_value,
                    "pdt_hold_days": f.pdt_hold_days,
                    "production_ready": f.is_production_ready,
                    "priority": f.priority.value,
                }
                for f in self.strategy_findings
            ],
            "cross_track_patterns": self.cross_track_patterns,
            "promotion_candidates": [
                {"strategy": f.strategy, "symbol": f.symbol, "sharpe": f.sharpe}
                for f in self.promotion_candidates
            ],
            "next_leads": self.next_leads,
            "stats": {
                "agents_executed": self.agents_executed,
                "agents_succeeded": self.agents_succeeded,
                "duration_seconds": self.total_duration_seconds,
            },
        }

    def to_markdown(self) -> str:
        """Generate markdown summary for human review."""
        lines = [
            f"# Research Cycle Report",
            f"",
            f"**Cycle ID**: {self.cycle_id}",
            f"**Focus**: {self.focus}",
            f"**Duration**: {self.total_duration_seconds:.1f}s",
            f"**Agents**: {self.agents_succeeded}/{self.agents_executed} succeeded",
            f"",
        ]

        # Regime Assessment
        if self.regime_assessment:
            lines.extend([
                "## Current Regime",
                f"- **Classification**: {self.regime_assessment.regime}",
                f"- **Confidence**: {self.regime_assessment.confidence:.0%}",
                f"- **Recommended**: {', '.join(self.regime_assessment.recommended_strategies)}",
                "",
            ])

        # Novel Patterns
        if self.novel_patterns:
            lines.extend([
                "## Novel Pattern Findings",
                "",
            ])
            for i, p in enumerate(self.novel_patterns, 1):
                priority_marker = {"critical": "!!", "high": "!", "medium": "", "low": ""}
                marker = priority_marker.get(p.priority.value, "")
                actionable = "(Actionable)" if p.actionable else ""
                lines.append(f"{i}. [{p.priority.value.upper()}{marker}] {p.description} {actionable}")
                lines.append(f"   - Evidence: {', '.join(p.evidence[:3])}")
                if p.recommended_strategy:
                    lines.append(f"   - Strategy: {p.recommended_strategy}")
                lines.append("")

        # Strategy Results
        if self.strategy_findings:
            lines.extend([
                "## Strategy Results",
                "",
                "| Strategy | Symbol | Sharpe | p-value | PDT Hold | Status |",
                "|----------|--------|--------|---------|----------|--------|",
            ])
            for f in sorted(self.strategy_findings, key=lambda x: x.sharpe, reverse=True)[:10]:
                status = "PROMOTE?" if f.is_production_ready else ("Significant" if f.is_significant else "-")
                lines.append(
                    f"| {f.strategy} | {f.symbol} | {f.sharpe:.2f} | {f.p_value:.4f} | {f.pdt_hold_days}d | {status} |"
                )
            lines.append("")

        # Cross-Track Patterns
        if self.cross_track_patterns:
            lines.extend([
                "## Cross-Track Patterns",
                "",
            ])
            for pattern in self.cross_track_patterns:
                lines.append(f"- {pattern.get('description', 'Pattern detected')}")
            lines.append("")

        # Promotion Candidates
        if self.promotion_candidates:
            lines.extend([
                "## Promotion Candidates (Require Approval)",
                "",
            ])
            for f in self.promotion_candidates:
                lines.append(f"- [ ] {f.strategy}/{f.symbol} → budget_pool ({f.pdt_hold_days}d hold)")
            lines.append("")

        # Next Leads
        if self.next_leads:
            lines.extend([
                "## Suggested Next Priorities",
                "",
            ])
            for i, lead in enumerate(self.next_leads, 1):
                priority = lead.get("priority", 0.5)
                lines.append(f"{i}. {lead.get('description', 'Follow-up')} (priority: {priority:.1f})")
            lines.append("")

        return "\n".join(lines)


class ResearchResultAggregator:
    """
    Combine results from parallel research agents.

    Merges findings, deduplicates, ranks strategies, and identifies
    cross-track patterns between novel research and strategy testing.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or "/home/nock/quant_results/consolidated_reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def aggregate(
        self,
        results: list[AgentResult],
        cycle_id: str,
        focus: str
    ) -> ConsolidatedReport:
        """
        Aggregate results from multiple agents into a consolidated report.

        Args:
            results: List of AgentResult from parallel execution
            cycle_id: Unique identifier for this research cycle
            focus: Research focus area

        Returns:
            ConsolidatedReport with all findings consolidated
        """
        started_at = min(r.started_at for r in results) if results else datetime.now()
        completed_at = max(r.completed_at for r in results) if results else datetime.now()

        # Parse results by track
        novel_patterns = []
        regime_assessment = None
        strategy_findings = []

        for result in results:
            if result.status != TaskStatus.COMPLETED:
                continue

            if result.agent_type in [AgentType.MACRO_RESEARCH, AgentType.NEWS_ANALYST]:
                patterns = self._parse_novel_patterns(result)
                novel_patterns.extend(patterns)

            elif result.agent_type == AgentType.REGIME_DETECTOR:
                regime_assessment = self._parse_regime_assessment(result)

            elif result.agent_type == AgentType.RESEARCH_WORKER:
                findings = self._parse_strategy_findings(result)
                strategy_findings.extend(findings)

        # Deduplicate strategy findings
        strategy_findings = self._dedupe_strategies(strategy_findings)

        # Identify cross-track patterns
        cross_track = self.identify_cross_track_patterns(novel_patterns, strategy_findings)

        # Get promotion candidates
        promotion_candidates = [f for f in strategy_findings if f.is_production_ready]

        # Generate next leads
        next_leads = self._generate_next_leads(strategy_findings, novel_patterns, regime_assessment)

        report = ConsolidatedReport(
            cycle_id=cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            focus=focus,
            novel_patterns=novel_patterns,
            regime_assessment=regime_assessment,
            strategy_findings=strategy_findings,
            cross_track_patterns=cross_track,
            promotion_candidates=promotion_candidates,
            next_leads=next_leads,
            agents_executed=len(results),
            agents_succeeded=sum(1 for r in results if r.status == TaskStatus.COMPLETED),
            total_duration_seconds=(completed_at - started_at).total_seconds(),
        )

        self._save_report(report)
        return report

    def _parse_novel_patterns(self, result: AgentResult) -> list[NovelPattern]:
        """Parse novel patterns from macro/news agent output."""
        patterns = []

        # Look for structured patterns in output
        # This is a simplified parser - agents should output in structured format
        output = result.output

        # Pattern: [FINDING] description (confidence: 0.X)
        finding_matches = re.findall(
            r'\[FINDING\]\s*(.+?)\s*\(confidence:\s*([\d.]+)\)',
            output,
            re.IGNORECASE
        )

        for desc, conf in finding_matches:
            patterns.append(NovelPattern(
                pattern_type="macro_correlation" if result.agent_type == AgentType.MACRO_RESEARCH else "event_impact",
                description=desc.strip(),
                evidence=[],
                confidence=float(conf),
                actionable="actionable" in desc.lower() or "strategy" in desc.lower(),
                recommended_strategy=None,
                source_agent=result.agent_type.value,
                timestamp=result.completed_at,
            ))

        # If no structured patterns found, try to extract insights
        if not patterns and len(output) > 100:
            patterns.append(NovelPattern(
                pattern_type="general",
                description=f"Analysis from {result.agent_type.value}",
                evidence=[output[:200]],
                confidence=0.5,
                actionable=False,
                recommended_strategy=None,
                source_agent=result.agent_type.value,
                timestamp=result.completed_at,
            ))

        return patterns

    def _parse_regime_assessment(self, result: AgentResult) -> RegimeAssessment | None:
        """Parse regime assessment from detector output."""
        output = result.output

        # Look for regime classification
        regime_match = re.search(
            r'regime[:\s]*(risk_on|risk_off|range_bound|trending|rotation)',
            output,
            re.IGNORECASE
        )

        if not regime_match:
            return None

        regime = regime_match.group(1).lower()

        # Look for confidence
        conf_match = re.search(r'confidence[:\s]*([\d.]+)', output, re.IGNORECASE)
        confidence = float(conf_match.group(1)) if conf_match else 0.6

        # Map regimes to strategies
        regime_strategies = {
            "risk_on": (["momentum", "growth", "breakout"], ["defensive", "volatility_short"]),
            "risk_off": (["defensive", "volatility_long"], ["momentum", "growth"]),
            "range_bound": (["mean_reversion", "bollinger_reversal"], ["trend_following"]),
            "trending": (["trend_following", "momentum"], ["mean_reversion"]),
            "rotation": (["sector_momentum"], []),
        }

        recommended, avoid = regime_strategies.get(regime, ([], []))

        return RegimeAssessment(
            regime=regime,
            confidence=confidence,
            recommended_strategies=recommended,
            avoid_strategies=avoid,
            key_indicators={},
            timestamp=result.completed_at,
        )

    def _parse_strategy_findings(self, result: AgentResult) -> list[StrategyFinding]:
        """Parse strategy findings from research worker output."""
        findings = []
        output = result.output

        # Look for strategy results in various formats
        # Format 1: strategy/SYMBOL: Sharpe=X.XX, p=0.XXXX
        pattern1 = re.findall(
            r'(\w+)/(\w+)[:\s]+Sharpe[=:\s]*([\d.]+)[,\s]+p[=:\s]*([\d.]+)',
            output
        )

        for strategy, symbol, sharpe, p_value in pattern1:
            findings.append(StrategyFinding(
                strategy=strategy,
                symbol=symbol,
                sharpe=float(sharpe),
                p_value=float(p_value),
                pdt_hold_days=2,  # Default, should be parsed
                source_agent=result.agent_type.value,
                timestamp=result.completed_at,
            ))

        # Format 2: | strategy | symbol | sharpe | p_value |
        pattern2 = re.findall(
            r'\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)',
            output
        )

        for strategy, symbol, sharpe, p_value in pattern2:
            if strategy.lower() not in ['strategy', '---', '===']:
                findings.append(StrategyFinding(
                    strategy=strategy,
                    symbol=symbol,
                    sharpe=float(sharpe),
                    p_value=float(p_value),
                    pdt_hold_days=2,
                    source_agent=result.agent_type.value,
                    timestamp=result.completed_at,
                ))

        return findings

    def _dedupe_strategies(self, findings: list[StrategyFinding]) -> list[StrategyFinding]:
        """Deduplicate strategy findings, keeping best result for each combo."""
        best: dict[tuple[str, str], StrategyFinding] = {}

        for f in findings:
            key = (f.strategy, f.symbol)
            if key not in best or f.sharpe > best[key].sharpe:
                best[key] = f

        return list(best.values())

    def identify_cross_track_patterns(
        self,
        novel_patterns: list[NovelPattern],
        strategy_findings: list[StrategyFinding]
    ) -> list[dict]:
        """
        Find patterns connecting macro factors to strategy performance.

        Look for correlations between novel pattern findings and
        strategy results that might indicate causal relationships.
        """
        cross_patterns = []

        # Look for sector overlaps
        for pattern in novel_patterns:
            if pattern.confidence < 0.5:
                continue

            # Check if any strategies performed well in mentioned sectors
            relevant_findings = [
                f for f in strategy_findings
                if f.is_significant and self._pattern_relates_to_symbol(pattern, f.symbol)
            ]

            if relevant_findings:
                cross_patterns.append({
                    "type": "macro_strategy_correlation",
                    "description": f"Macro pattern '{pattern.description[:50]}...' may relate to {len(relevant_findings)} significant strategies",
                    "pattern": pattern.description,
                    "strategies": [f"{f.strategy}/{f.symbol}" for f in relevant_findings[:3]],
                    "confidence": pattern.confidence * 0.8,  # Discount for indirect relationship
                })

        return cross_patterns

    def _pattern_relates_to_symbol(self, pattern: NovelPattern, symbol: str) -> bool:
        """Check if pattern description relates to a symbol."""
        desc_lower = pattern.description.lower()

        # Sector mappings
        sector_keywords = {
            "tech": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "QQQ", "XLK"],
            "semiconductor": ["NVDA", "AMD", "QCOM", "MU", "MRVL", "AVGO"],
            "financial": ["JPM", "GS", "V", "MA", "BAC", "XLF"],
            "energy": ["XOM", "CVX", "COP", "SLB", "XLE"],
        }

        for sector, symbols in sector_keywords.items():
            if sector in desc_lower and symbol in symbols:
                return True

        return symbol in pattern.description.upper()

    def _generate_next_leads(
        self,
        strategy_findings: list[StrategyFinding],
        novel_patterns: list[NovelPattern],
        regime: RegimeAssessment | None
    ) -> list[dict]:
        """Generate research leads for next cycle."""
        leads = []

        # Lead 1: Extend successful strategies to similar symbols
        successful = [f for f in strategy_findings if f.is_significant]
        if successful:
            best = max(successful, key=lambda x: x.sharpe)
            leads.append({
                "description": f"Test {best.strategy} on more symbols in same sector",
                "priority": 0.8,
                "rationale": f"Strong results on {best.symbol} (Sharpe={best.sharpe:.2f})",
            })

        # Lead 2: Test regime-recommended strategies
        if regime and regime.recommended_strategies:
            leads.append({
                "description": f"Test {', '.join(regime.recommended_strategies[:2])} during current {regime.regime} regime",
                "priority": 0.7,
                "rationale": f"Regime detector confidence: {regime.confidence:.0%}",
            })

        # Lead 3: Follow up on high-confidence novel patterns
        actionable_patterns = [p for p in novel_patterns if p.actionable and p.confidence > 0.6]
        for pattern in actionable_patterns[:2]:
            leads.append({
                "description": f"Investigate: {pattern.description[:60]}",
                "priority": pattern.confidence,
                "rationale": "Novel pattern requires validation",
            })

        # Sort by priority
        leads.sort(key=lambda x: x["priority"], reverse=True)
        return leads[:5]

    def _save_report(self, report: ConsolidatedReport) -> None:
        """Save report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON
        json_path = self.output_dir / f"{timestamp}_{report.cycle_id}.json"
        with open(json_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)

        # Save Markdown
        md_path = self.output_dir / f"{timestamp}_{report.cycle_id}.md"
        with open(md_path, "w") as f:
            f.write(report.to_markdown())
