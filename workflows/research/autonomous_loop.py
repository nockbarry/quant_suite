"""
Autonomous research loop orchestrator.

Main entry point for running extended autonomous research sessions.
Generates hypotheses, runs experiments, accumulates knowledge, and
produces actionable insights without human intervention.
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_RESULTS_DIR = Path(os.environ.get("QUANT_RESULTS_DIR", str(Path.home() / "quant_results")))

from .data_hub import DataHub
from .experiment_runner import ExperimentResult, ExperimentRunner
from .hypothesis_engine import Hypothesis, HypothesisEngine
from .knowledge_base import KnowledgeBase


@dataclass
class CycleReport:
    """Report for a single research cycle."""
    cycle_number: int
    hypotheses_tested: int
    significant_results: int
    best_sharpe: float
    best_strategy: str | None
    insights_generated: int
    runtime_seconds: float


@dataclass
class ResearchReport:
    """Final report for autonomous research session."""
    session_id: str
    session_path: Path
    start_time: datetime
    end_time: datetime
    total_runtime: timedelta

    # Aggregate stats
    total_cycles: int
    total_experiments: int
    total_significant: int
    success_rate: float

    # Best results
    best_strategies: list[dict]
    key_insights: list[str]

    # Cycle breakdown
    cycle_reports: list[CycleReport]

    # Files generated
    report_files: list[Path]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "session_path": str(self.session_path),
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "total_runtime_hours": self.total_runtime.total_seconds() / 3600,
            "total_cycles": self.total_cycles,
            "total_experiments": self.total_experiments,
            "total_significant": self.total_significant,
            "success_rate": self.success_rate,
            "best_strategies": self.best_strategies,
            "key_insights": self.key_insights,
            "report_files": [str(p) for p in self.report_files],
        }


# Default stock universe for research
DEFAULT_UNIVERSE = [
    # Large cap tech
    "AAPL", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
    # Semiconductors
    "AMD", "AVGO", "QCOM",
    # Growth
    "CRWD", "NET", "PLTR",
    # ETFs
    "QQQ", "SPY", "IWM",
    # Financials
    "JPM", "GS",
]


class AutonomousResearcher:
    """
    Autonomous research loop that:
    1. Generates hypotheses based on past learnings
    2. Fetches required data
    3. Runs MCPT validation experiments
    4. Records insights
    5. Generates reports
    6. Repeats with improved hypotheses
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        max_runtime_hours: float = 4.0,
        experiments_per_cycle: int = 10,
        validation_periods: list[int] | None = None,
        n_permutations: int = 200,
        output_dir: Path | None = None,
    ):
        self.symbols = symbols or DEFAULT_UNIVERSE
        self.max_runtime = timedelta(hours=max_runtime_hours)
        self.experiments_per_cycle = experiments_per_cycle
        self.validation_periods = validation_periods or [90, 180]
        self.n_permutations = n_permutations
        self.output_dir = output_dir or _RESULTS_DIR

        # Initialize components
        self.hub = DataHub()
        self.kb = KnowledgeBase()
        self.hypothesis_engine = HypothesisEngine(self.kb, self.symbols)
        self.experiment_runner = ExperimentRunner(self.hub, self.kb)

        # Session tracking
        self.session_id: str | None = None
        self.session_path: Path | None = None
        self.all_results: list[ExperimentResult] = []
        self.cycle_reports: list[CycleReport] = []

    async def run(self) -> ResearchReport:
        """Run autonomous research loop."""
        start_time = datetime.now()
        self._create_session()

        print(f"\n{'='*60}")
        print(f"AUTONOMOUS RESEARCH SESSION: {self.session_id}")
        print(f"{'='*60}")
        print(f"Symbols: {len(self.symbols)} stocks")
        print(f"Max runtime: {self.max_runtime}")
        print(f"Experiments per cycle: {self.experiments_per_cycle}")
        print(f"Output: {self.session_path}")
        print(f"{'='*60}\n")

        # Pre-fetch data for all symbols
        print("Prefetching data for all symbols...")
        data_bundle = None
        try:
            data_bundle = await self.hub.fetch_all(
                self.symbols,
                start=datetime.now() - timedelta(days=730),  # 2 years
                end=datetime.now(),
            )
            print(f"  Loaded price data for {len(data_bundle.price_data)} symbols")
        except Exception as e:
            print(f"Warning: Data prefetch had issues: {e}")
            # Create empty bundle as fallback
            from .data_hub import DataBundle, EconomicRegime
            data_bundle = DataBundle(
                symbols=self.symbols,
                start_date=datetime.now() - timedelta(days=730),
                end_date=datetime.now(),
                price_data={},
                insider_signals={},
                economic_regime=None,
                sentiment_scores={},
                news_headlines={},
                data_quality={},
            )

        cycle = 0
        while datetime.now() - start_time < self.max_runtime:
            cycle += 1
            cycle_start = datetime.now()

            print(f"\n{'='*50}")
            print(f"RESEARCH CYCLE {cycle}")
            print(f"{'='*50}")

            # 1. Generate hypotheses
            print(f"\n[1/4] Generating {self.experiments_per_cycle} hypotheses...")
            hypotheses = self.hypothesis_engine.generate_hypotheses(
                n=self.experiments_per_cycle,
                symbols=self.symbols,
            )

            if not hypotheses:
                print("No new hypotheses to test. Stopping.")
                break

            # Show hypothesis summary
            summary = self.hypothesis_engine.get_hypothesis_summary(hypotheses)
            print(f"  Sources: {summary['by_source']}")
            print(f"  Avg priority: {summary['avg_priority']:.2f}")

            # 2. Run experiments
            print(f"\n[2/4] Running {len(hypotheses)} experiments...")
            results = await self.experiment_runner.run_batch(
                hypotheses,
                data_bundle,
                validation_days=self.validation_periods[0],
                n_permutations=self.n_permutations,
            )
            self.all_results.extend(results)

            # 3. Process results and update knowledge
            print("\n[3/4] Processing results...")
            significant = [r for r in results if r.is_significant]
            print(f"  Significant: {len(significant)}/{len(results)}")

            for result in results:
                self._process_result(result)

            # 4. Generate cycle report
            print("\n[4/4] Saving cycle report...")
            cycle_runtime = (datetime.now() - cycle_start).total_seconds()
            cycle_report = CycleReport(
                cycle_number=cycle,
                hypotheses_tested=len(results),
                significant_results=len(significant),
                best_sharpe=max((r.val_sharpe for r in results), default=0.0),
                best_strategy=significant[0].hypothesis.name if significant else None,
                insights_generated=len([r for r in results if r.insights]),
                runtime_seconds=cycle_runtime,
            )
            self.cycle_reports.append(cycle_report)
            self._save_cycle_report(cycle_report, results)

            # Print cycle summary
            elapsed = datetime.now() - start_time
            remaining = self.max_runtime - elapsed
            print(f"\n  Cycle {cycle} complete in {cycle_runtime:.1f}s")
            print(f"  Time remaining: {remaining}")

            # 5. Check for early stopping
            if self._should_stop_early(results):
                print("\nEarly stopping: Diminishing returns detected")
                break

        # Generate final report
        end_time = datetime.now()
        return self._generate_final_report(start_time, end_time)

    def _create_session(self) -> None:
        """Create session directory and ID."""
        import hashlib
        import random

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        hash_suffix = hashlib.md5(
            f"{timestamp}_{random.random()}".encode()
        ).hexdigest()[:6]

        self.session_id = f"autonomous_research_{hash_suffix}"
        self.session_path = self.output_dir / "sessions" / f"{timestamp}_{self.session_id}"
        self.session_path.mkdir(parents=True, exist_ok=True)

        # Create data subdirectory
        (self.session_path / "data").mkdir(exist_ok=True)
        (self.session_path / "cycles").mkdir(exist_ok=True)

        # Save session metadata
        metadata = {
            "session_id": self.session_id,
            "start_time": datetime.now().isoformat(),
            "symbols": self.symbols,
            "max_runtime_hours": self.max_runtime.total_seconds() / 3600,
            "experiments_per_cycle": self.experiments_per_cycle,
            "validation_periods": self.validation_periods,
            "n_permutations": self.n_permutations,
        }
        (self.session_path / "metadata.json").write_text(
            json.dumps(metadata, indent=2)
        )

    def _process_result(self, result: ExperimentResult) -> None:
        """Process experiment result and update knowledge base."""
        hypothesis = result.hypothesis

        if result.status == "error":
            self.kb.record_failure(
                strategy_name=hypothesis.strategy_type,
                symbol=hypothesis.symbols[0],
                params=hypothesis.strategy_params,
                reason=f"Error: {result.error_message}",
                session_id=self.session_id,
            )
            return

        # Mark as tested
        self.kb.mark_tested(
            hypothesis.strategy_type,
            hypothesis.symbols[0],
            hypothesis.strategy_params,
        )

        if result.is_significant:
            # Record success
            self.kb.record_success(
                strategy_name=hypothesis.strategy_type,
                symbol=hypothesis.symbols[0],
                params=hypothesis.strategy_params,
                train_sharpe=result.train_sharpe,
                val_sharpe=result.val_sharpe,
                p_value=result.mcpt_p_value,
                session_id=self.session_id,
                validation_period=f"{self.validation_periods[0]}d",
            )

            # Add insight
            self.kb.add_insight(
                category="strategy",
                content=f"{hypothesis.strategy_type} shows significance on {hypothesis.symbols[0]} "
                        f"(p={result.mcpt_p_value:.3f}, Sharpe={result.val_sharpe:.2f})",
                evidence=[self.session_id],
                confidence=min(0.9, 1 - result.mcpt_p_value),
                tags=[hypothesis.strategy_type, hypothesis.symbols[0], "significant"],
            )
        else:
            # Record failure
            self.kb.record_failure(
                strategy_name=hypothesis.strategy_type,
                symbol=hypothesis.symbols[0],
                params=hypothesis.strategy_params,
                reason=f"Not significant: p={result.mcpt_p_value:.3f}",
                session_id=self.session_id,
            )

    def _save_cycle_report(
        self,
        cycle_report: CycleReport,
        results: list[ExperimentResult],
    ) -> None:
        """Save cycle report to disk."""
        cycle_dir = self.session_path / "cycles" / f"cycle_{cycle_report.cycle_number:03d}"
        cycle_dir.mkdir(exist_ok=True)

        # Save cycle summary
        summary = {
            "cycle_number": cycle_report.cycle_number,
            "hypotheses_tested": cycle_report.hypotheses_tested,
            "significant_results": cycle_report.significant_results,
            "best_sharpe": cycle_report.best_sharpe,
            "best_strategy": cycle_report.best_strategy,
            "runtime_seconds": cycle_report.runtime_seconds,
        }
        (cycle_dir / "summary.json").write_text(json.dumps(summary, indent=2))

        # Save all results (convert numpy types to Python native)
        results_data = []
        for r in results:
            results_data.append({
                "hypothesis_id": r.hypothesis.id,
                "hypothesis_name": r.hypothesis.name,
                "strategy_type": r.hypothesis.strategy_type,
                "symbol": r.hypothesis.symbols[0],
                "status": r.status,
                "train_sharpe": float(r.train_sharpe),
                "val_sharpe": float(r.val_sharpe),
                "p_value": float(r.mcpt_p_value),
                "is_significant": bool(r.is_significant),
                "insights": list(r.insights),
            })
        (cycle_dir / "results.json").write_text(json.dumps(results_data, indent=2))

    def _should_stop_early(self, recent_results: list[ExperimentResult]) -> bool:
        """Check if we should stop early due to diminishing returns."""
        # Continue if we're finding significant results
        if any(r.is_significant for r in recent_results):
            return False

        # Stop if last 3 cycles had no significant results
        if len(self.cycle_reports) >= 3:
            last_3_significant = sum(
                c.significant_results for c in self.cycle_reports[-3:]
            )
            if last_3_significant == 0:
                return True

        return False

    def _generate_final_report(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> ResearchReport:
        """Generate final research report."""
        total_runtime = end_time - start_time

        # Gather significant results
        significant_results = [r for r in self.all_results if r.is_significant]
        significant_results.sort(key=lambda r: r.val_sharpe, reverse=True)

        # Best strategies
        best_strategies = []
        for r in significant_results[:10]:
            best_strategies.append({
                "strategy": r.hypothesis.strategy_type,
                "symbol": r.hypothesis.symbols[0],
                "params": r.hypothesis.strategy_params,
                "val_sharpe": r.val_sharpe,
                "p_value": r.mcpt_p_value,
            })

        # Key insights
        key_insights = self.kb.get_insights(min_confidence=0.6)
        insight_texts = [i.content for i in key_insights[:20]]

        # Create report
        report = ResearchReport(
            session_id=self.session_id,
            session_path=self.session_path,
            start_time=start_time,
            end_time=end_time,
            total_runtime=total_runtime,
            total_cycles=len(self.cycle_reports),
            total_experiments=len(self.all_results),
            total_significant=len(significant_results),
            success_rate=len(significant_results) / max(1, len(self.all_results)),
            best_strategies=best_strategies,
            key_insights=insight_texts,
            cycle_reports=self.cycle_reports,
            report_files=[],
        )

        # Save final report
        report_files = self._save_final_report(report)
        report.report_files = report_files

        # Print summary
        print(f"\n{'='*60}")
        print("AUTONOMOUS RESEARCH COMPLETE")
        print(f"{'='*60}")
        print(f"Session: {self.session_id}")
        print(f"Runtime: {total_runtime}")
        print(f"Cycles: {report.total_cycles}")
        print(f"Experiments: {report.total_experiments}")
        print(f"Significant: {report.total_significant} ({report.success_rate:.1%})")
        print(f"\nBest strategies:")
        for s in best_strategies[:5]:
            print(f"  - {s['strategy']} on {s['symbol']}: "
                  f"Sharpe={s['val_sharpe']:.2f}, p={s['p_value']:.3f}")
        print(f"\nReports saved to: {self.session_path}")
        print(f"{'='*60}\n")

        return report

    def _save_final_report(self, report: ResearchReport) -> list[Path]:
        """Save final report files."""
        report_files = []

        # 1. JSON summary
        json_path = self.session_path / "report.json"
        json_path.write_text(json.dumps(report.to_dict(), indent=2))
        report_files.append(json_path)

        # 2. Markdown summary
        md_path = self.session_path / "RESEARCH_SUMMARY.md"
        md_content = self._generate_markdown_report(report)
        md_path.write_text(md_content)
        report_files.append(md_path)

        # 3. All results CSV
        csv_path = self.session_path / "data" / "all_experiments.csv"
        self._save_results_csv(csv_path)
        report_files.append(csv_path)

        # 4. Significant results CSV
        sig_csv_path = self.session_path / "data" / "significant_results.csv"
        self._save_significant_csv(sig_csv_path)
        report_files.append(sig_csv_path)

        # 5. Knowledge base snapshot
        kb_path = self.session_path / "data" / "knowledge_snapshot.json"
        kb_path.write_text(json.dumps(self.kb.summary(), indent=2))
        report_files.append(kb_path)

        return report_files

    def _generate_markdown_report(self, report: ResearchReport) -> str:
        """Generate markdown summary report."""
        lines = [
            "# Autonomous Research Report",
            "",
            f"**Session**: {report.session_id}",
            f"**Generated**: {report.end_time.strftime('%Y-%m-%d %H:%M')}",
            f"**Runtime**: {report.total_runtime}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            f"- **Total experiments**: {report.total_experiments}",
            f"- **Significant results**: {report.total_significant} ({report.success_rate:.1%})",
            f"- **Research cycles**: {report.total_cycles}",
            "",
            "---",
            "",
            "## Best Strategies",
            "",
            "| Strategy | Symbol | Sharpe | p-value |",
            "|----------|--------|--------|---------|",
        ]

        for s in report.best_strategies[:10]:
            lines.append(
                f"| {s['strategy']} | {s['symbol']} | "
                f"{s['val_sharpe']:.2f} | {s['p_value']:.3f} |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Key Insights",
            "",
        ])

        for i, insight in enumerate(report.key_insights[:15], 1):
            lines.append(f"{i}. {insight}")

        lines.extend([
            "",
            "---",
            "",
            "## Cycle Summary",
            "",
            "| Cycle | Tested | Significant | Best Sharpe | Runtime |",
            "|-------|--------|-------------|-------------|---------|",
        ])

        for c in report.cycle_reports:
            lines.append(
                f"| {c.cycle_number} | {c.hypotheses_tested} | "
                f"{c.significant_results} | {c.best_sharpe:.2f} | "
                f"{c.runtime_seconds:.1f}s |"
            )

        lines.extend([
            "",
            "---",
            "",
            "## Knowledge Base Summary",
            "",
            f"```json",
            json.dumps(self.kb.summary(), indent=2),
            "```",
            "",
            "---",
            "",
            "*Generated by Autonomous Research System*",
        ])

        return "\n".join(lines)

    def _save_results_csv(self, path: Path) -> None:
        """Save all results to CSV."""
        lines = [
            "hypothesis_id,hypothesis_name,strategy_type,symbol,status,"
            "train_sharpe,val_sharpe,p_value,is_significant"
        ]

        for r in self.all_results:
            lines.append(
                f"{r.hypothesis.id},{r.hypothesis.name},{r.hypothesis.strategy_type},"
                f"{r.hypothesis.symbols[0]},{r.status},{r.train_sharpe:.4f},"
                f"{r.val_sharpe:.4f},{r.mcpt_p_value:.4f},{r.is_significant}"
            )

        path.write_text("\n".join(lines))

    def _save_significant_csv(self, path: Path) -> None:
        """Save significant results to CSV."""
        significant = [r for r in self.all_results if r.is_significant]

        lines = [
            "strategy_type,symbol,params,train_sharpe,val_sharpe,p_value"
        ]

        for r in significant:
            params_str = json.dumps(r.hypothesis.strategy_params).replace(",", ";")
            lines.append(
                f"{r.hypothesis.strategy_type},{r.hypothesis.symbols[0]},"
                f"\"{params_str}\",{r.train_sharpe:.4f},"
                f"{r.val_sharpe:.4f},{r.mcpt_p_value:.4f}"
            )

        path.write_text("\n".join(lines))


async def run_autonomous_research(
    symbols: list[str] | None = None,
    hours: float = 2.0,
    experiments_per_cycle: int = 10,
    n_permutations: int = 200,
    output_dir: Path | None = None,
) -> ResearchReport:
    """
    Main entry point for autonomous research.

    Args:
        symbols: Stock symbols to research. Defaults to broad universe.
        hours: Maximum runtime in hours.
        experiments_per_cycle: Hypotheses to test per cycle.
        n_permutations: MCPT permutations per test.
        output_dir: Output directory for results.

    Returns:
        ResearchReport with all results and insights.

    Example:
        from workflows.research import run_autonomous_research

        report = await run_autonomous_research(
            symbols=["AAPL", "NVDA", "AMZN", "QQQ", "SPY"],
            hours=2.0
        )
        print(f"Report: {report.session_path}/RESEARCH_SUMMARY.md")
    """
    researcher = AutonomousResearcher(
        symbols=symbols,
        max_runtime_hours=hours,
        experiments_per_cycle=experiments_per_cycle,
        n_permutations=n_permutations,
        output_dir=output_dir,
    )
    return await researcher.run()


def run_research_sync(
    symbols: list[str] | None = None,
    hours: float = 2.0,
    experiments_per_cycle: int = 10,
) -> ResearchReport:
    """
    Synchronous wrapper for autonomous research.

    Example:
        from workflows.research.autonomous_loop import run_research_sync
        report = run_research_sync(hours=1.0)
    """
    return asyncio.run(run_autonomous_research(
        symbols=symbols,
        hours=hours,
        experiments_per_cycle=experiments_per_cycle,
    ))


if __name__ == "__main__":
    # Example usage
    import sys

    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5

    print(f"Running autonomous research for {hours} hours...")
    report = run_research_sync(hours=hours)
    print(f"\nResults saved to: {report.session_path}")
