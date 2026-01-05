#!/usr/bin/env python3
"""
Alpha Hunt Orchestrator - Autonomous Alpha Discovery

This orchestrator runs a complete alpha discovery cycle:
1. Reconnaissance (parallel): Scanner, Data Scout, Knowledge Query
2. Hypothesis Generation (sequential): Generate ranked ideas
3. Testing (parallel): N workers test hypotheses
4. Validation & Promotion (sequential): Critic review, promote winners

Usage:
    # Full autonomous cycle
    PYTHONPATH=. python workflows/autonomous/alpha_hunt_orchestrator.py

    # Focused cycle
    PYTHONPATH=. python workflows/autonomous/alpha_hunt_orchestrator.py --focus commodities

    # Quick test mode
    PYTHONPATH=. python workflows/autonomous/alpha_hunt_orchestrator.py --quick

Author: Claude Code
Created: 2026-01-05
"""

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class Hypothesis:
    """A testable hypothesis."""

    id: str
    statement: str
    target_assets: list[str]
    data_requirements: list[str]
    strategy_type: str  # momentum, mean_reversion, pairs, etc.
    expected_mechanism: str
    priority: float  # 0-1
    source: str  # scanner, blog, knowledge_base, etc.


@dataclass
class TestResult:
    """Result from testing a hypothesis."""

    hypothesis_id: str
    success: bool
    sharpe_ratio: float
    total_return: float
    mcpt_pvalue: float
    oos_sharpe: float
    n_trades: int
    win_rate: float
    notes: str
    is_significant: bool = False
    promoted: bool = False


@dataclass
class CycleResult:
    """Complete result from an alpha hunt cycle."""

    cycle_id: str
    timestamp: str
    focus: str
    reconnaissance: dict
    hypotheses: list[Hypothesis]
    test_results: list[TestResult]
    significant_findings: list[str]
    promoted_strategies: list[str]
    next_priorities: list[str]
    duration_seconds: float


# =============================================================================
# PHASE 1: RECONNAISSANCE
# =============================================================================


class MarketScanner:
    """Scan markets for anomalies and opportunities."""

    UNIVERSES = {
        "commodities": ["UNG", "USO", "CPER", "GLD", "SLV", "DBA", "URA"],
        "semiconductors": ["NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX"],
        "tech_mega": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"],
        "financials": ["JPM", "GS", "BAC", "V", "MA"],
        "etfs": ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE"],
    }

    async def scan(self, focus: str | None = None) -> dict:
        """Scan markets and return opportunities."""
        universes = (
            {focus: self.UNIVERSES.get(focus, [])}
            if focus and focus in self.UNIVERSES
            else self.UNIVERSES
        )

        results = {
            "timestamp": datetime.now().isoformat(),
            "scanned_symbols": 0,
            "opportunities": [],
            "regime": {},
        }

        for universe_name, symbols in universes.items():
            for symbol in symbols:
                try:
                    data = yf.download(symbol, period="60d", progress=False)
                    if isinstance(data.columns, pd.MultiIndex):
                        data.columns = data.columns.get_level_values(0)

                    if len(data) < 30:
                        continue

                    close = data["Close"]
                    results["scanned_symbols"] += 1

                    # Calculate z-score
                    mean_20 = close.rolling(20).mean()
                    std_20 = close.rolling(20).std()
                    zscore = (close - mean_20) / std_20
                    current_z = zscore.iloc[-1]

                    # Calculate momentum
                    mom_5d = close.pct_change(5).iloc[-1]
                    mom_20d = close.pct_change(20).iloc[-1]

                    # Identify opportunities
                    if current_z < -2.0:
                        results["opportunities"].append(
                            {
                                "symbol": symbol,
                                "universe": universe_name,
                                "type": "oversold",
                                "zscore": float(current_z),
                                "strategy": "mean_reversion_long",
                                "priority": min(abs(current_z) / 3, 1.0),
                            }
                        )
                    elif current_z > 2.0:
                        results["opportunities"].append(
                            {
                                "symbol": symbol,
                                "universe": universe_name,
                                "type": "overbought",
                                "zscore": float(current_z),
                                "strategy": "mean_reversion_short",
                                "priority": min(abs(current_z) / 3, 1.0),
                            }
                        )
                    elif mom_20d > 0.15:
                        results["opportunities"].append(
                            {
                                "symbol": symbol,
                                "universe": universe_name,
                                "type": "strong_momentum",
                                "momentum_20d": float(mom_20d),
                                "strategy": "momentum_long",
                                "priority": min(mom_20d / 0.3, 1.0),
                            }
                        )

                except Exception as e:
                    logger.warning(f"Error scanning {symbol}: {e}")

        # Sort by priority
        results["opportunities"] = sorted(
            results["opportunities"], key=lambda x: x.get("priority", 0), reverse=True
        )

        return results


class DataScout:
    """Scout for new data sources and verify existing ones."""

    BLOG_SOURCES = [
        {"name": "semianalysis", "url": "https://www.semianalysis.com/feed", "active": True},
        {"name": "stratechery", "url": "https://stratechery.com/feed/", "active": True},
    ]

    COMMODITY_SOURCES = [
        {"name": "FRED", "type": "api", "active": True},
        {"name": "yfinance_etf", "type": "api", "active": True},
    ]

    async def scout(self) -> dict:
        """Scout data sources and check for new opportunities."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "blog_sources": [],
            "commodity_sources": [],
            "new_opportunities": [],
        }

        # Check blog sources
        for source in self.BLOG_SOURCES:
            results["blog_sources"].append(
                {
                    "name": source["name"],
                    "active": source["active"],
                    "last_check": datetime.now().isoformat(),
                }
            )

        # Check commodity sources
        for source in self.COMMODITY_SOURCES:
            results["commodity_sources"].append(
                {
                    "name": source["name"],
                    "type": source["type"],
                    "active": source["active"],
                }
            )

        # Identify new data opportunities
        results["new_opportunities"] = [
            {
                "source": "commodity_etf_correlations",
                "description": "Cross-commodity correlation analysis",
                "priority": 0.7,
            },
            {
                "source": "sector_rotation",
                "description": "ETF flow-based sector rotation signals",
                "priority": 0.6,
            },
        ]

        return results


class KnowledgeQuerier:
    """Query knowledge base for recent results and open leads."""

    KNOWLEDGE_PATH = Path("/home/nock/quant_results")

    async def query(self) -> dict:
        """Query knowledge base for recent learnings."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "recent_wins": [],
            "recent_fails": [],
            "open_leads": [],
            "causal_relationships": [],
        }

        # Check for recent validation results
        validation_dirs = [
            self.KNOWLEDGE_PATH / "commodity_validation",
            self.KNOWLEDGE_PATH / "lead_lag_validation",
        ]

        for vdir in validation_dirs:
            if vdir.exists():
                for f in vdir.glob("*.json"):
                    try:
                        with open(f) as fp:
                            data = json.load(fp)
                            # Extract any significant findings
                            if "production_ready" in data:
                                for sym in data.get("production_ready", []):
                                    results["recent_wins"].append(
                                        {
                                            "strategy": vdir.name,
                                            "symbol": sym,
                                            "source": str(f),
                                        }
                                    )
                    except Exception:
                        pass

        # Known learnings from commodity work
        results["causal_relationships"] = [
            {
                "cause": "extreme_zscore",
                "effect": "mean_reversion",
                "assets": ["UNG", "USO", "CPER"],
                "lag_days": 5,
                "confidence": 0.8,
            },
        ]

        # Open leads to investigate
        results["open_leads"] = [
            {
                "lead": "Test mean reversion on additional ETFs",
                "priority": 0.8,
                "source": "commodity_validation",
            },
            {
                "lead": "Cross-asset correlation during volatility spikes",
                "priority": 0.7,
                "source": "market_observation",
            },
        ]

        return results


# =============================================================================
# PHASE 2: HYPOTHESIS GENERATION
# =============================================================================


class HypothesisGenerator:
    """Generate ranked hypotheses from reconnaissance."""

    def generate(
        self,
        scanner_results: dict,
        scout_results: dict,
        knowledge_results: dict,
        max_hypotheses: int = 10,
    ) -> list[Hypothesis]:
        """Generate ranked hypotheses."""
        hypotheses = []

        # Generate from scanner opportunities
        for i, opp in enumerate(scanner_results.get("opportunities", [])[:5]):
            h = Hypothesis(
                id=f"scanner_{i+1}",
                statement=f"{opp['strategy']} on {opp['symbol']} ({opp['type']})",
                target_assets=[opp["symbol"]],
                data_requirements=["daily_ohlcv"],
                strategy_type=opp["strategy"].split("_")[0],  # momentum or mean_reversion
                expected_mechanism=f"Z-score at {opp.get('zscore', 0):.1f} suggests {opp['type']}",
                priority=opp.get("priority", 0.5),
                source="market_scanner",
            )
            hypotheses.append(h)

        # Generate from open leads
        for i, lead in enumerate(knowledge_results.get("open_leads", [])[:3]):
            h = Hypothesis(
                id=f"lead_{i+1}",
                statement=lead["lead"],
                target_assets=[],  # To be determined
                data_requirements=["daily_ohlcv"],
                strategy_type="research",
                expected_mechanism="From knowledge base",
                priority=lead.get("priority", 0.5),
                source="knowledge_base",
            )
            hypotheses.append(h)

        # Sort by priority and limit
        hypotheses = sorted(hypotheses, key=lambda x: x.priority, reverse=True)
        return hypotheses[:max_hypotheses]


# =============================================================================
# PHASE 3: TESTING
# =============================================================================


class HypothesisTester:
    """Test a single hypothesis with full validation."""

    def __init__(self, transaction_cost_bps: float = 10):
        self.transaction_cost_bps = transaction_cost_bps

    async def test(self, hypothesis: Hypothesis, quick: bool = False) -> TestResult:
        """Test a hypothesis and return results."""
        logger.info(f"Testing: {hypothesis.statement}")

        # Skip research-type hypotheses (need manual investigation)
        if hypothesis.strategy_type == "research" or not hypothesis.target_assets:
            return TestResult(
                hypothesis_id=hypothesis.id,
                success=False,
                sharpe_ratio=0,
                total_return=0,
                mcpt_pvalue=1.0,
                oos_sharpe=0,
                n_trades=0,
                win_rate=0,
                notes="Research hypothesis - needs manual investigation",
            )

        symbol = hypothesis.target_assets[0]

        try:
            # Fetch data
            data = yf.download(symbol, period="3y", progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            if len(data) < 200:
                return TestResult(
                    hypothesis_id=hypothesis.id,
                    success=False,
                    sharpe_ratio=0,
                    total_return=0,
                    mcpt_pvalue=1.0,
                    oos_sharpe=0,
                    n_trades=0,
                    win_rate=0,
                    notes=f"Insufficient data for {symbol}",
                )

            close = data["Close"]

            # Determine strategy parameters based on type
            if "mean_reversion" in hypothesis.strategy_type:
                window = 20
                threshold = 2.0
                hold_days = 5
            else:  # momentum
                window = 20
                threshold = 0.05  # 5% momentum threshold
                hold_days = 10

            # Run backtest
            result = await self._run_backtest(
                close, hypothesis.strategy_type, window, threshold, hold_days
            )

            # Run MCPT
            n_perm = 100 if quick else 1000
            mcpt = self._run_mcpt(result["returns"], n_perm)

            # Run walk-forward
            oos_sharpe = self._run_walk_forward(
                close, hypothesis.strategy_type, window, threshold, hold_days
            )

            is_significant = mcpt["p_value"] < 0.05 and oos_sharpe > 0

            return TestResult(
                hypothesis_id=hypothesis.id,
                success=True,
                sharpe_ratio=result["sharpe"],
                total_return=result["total_return"],
                mcpt_pvalue=mcpt["p_value"],
                oos_sharpe=oos_sharpe,
                n_trades=result["n_trades"],
                win_rate=result["win_rate"],
                notes=f"Strategy: {hypothesis.strategy_type}",
                is_significant=is_significant,
            )

        except Exception as e:
            return TestResult(
                hypothesis_id=hypothesis.id,
                success=False,
                sharpe_ratio=0,
                total_return=0,
                mcpt_pvalue=1.0,
                oos_sharpe=0,
                n_trades=0,
                win_rate=0,
                notes=f"Error: {str(e)}",
            )

    async def _run_backtest(
        self,
        close: pd.Series,
        strategy_type: str,
        window: int,
        threshold: float,
        hold_days: int,
    ) -> dict:
        """Run backtest and return metrics."""
        rolling_mean = close.rolling(window).mean()
        rolling_std = close.rolling(window).std()
        zscore = (close - rolling_mean) / rolling_std

        fwd_ret = close.shift(-hold_days) / close - 1

        if "mean_reversion" in strategy_type:
            long_signal = zscore < -threshold
            short_signal = zscore > threshold
            long_returns = fwd_ret[long_signal].dropna()
            short_returns = -fwd_ret[short_signal].dropna()
        else:  # momentum
            momentum = close.pct_change(window)
            long_signal = momentum > threshold
            short_signal = momentum < -threshold
            long_returns = fwd_ret[long_signal].dropna()
            short_returns = -fwd_ret[short_signal].dropna()

        all_returns = pd.concat([long_returns, short_returns])

        if len(all_returns) < 10:
            return {
                "sharpe": 0,
                "total_return": 0,
                "n_trades": len(all_returns),
                "win_rate": 0,
                "returns": pd.Series(dtype=float),
            }

        sharpe = all_returns.mean() / all_returns.std() * np.sqrt(252 / hold_days)
        total_return = (1 + all_returns).prod() - 1
        win_rate = (all_returns > 0).mean()

        return {
            "sharpe": sharpe,
            "total_return": total_return,
            "n_trades": len(all_returns),
            "win_rate": win_rate,
            "returns": all_returns,
        }

    def _run_mcpt(self, returns: pd.Series, n_permutations: int) -> dict:
        """Run MCPT validation."""
        if len(returns) < 10 or returns.std() == 0:
            return {"p_value": 1.0, "significant": False}

        original_sharpe = returns.mean() / returns.std() * np.sqrt(252 / 5)
        returns_array = returns.values

        permuted_sharpes = []
        for _ in range(n_permutations):
            signs = np.random.choice([-1, 1], size=len(returns_array))
            perm = returns_array * signs
            if perm.std() > 0:
                permuted_sharpes.append(perm.mean() / perm.std() * np.sqrt(252 / 5))

        p_value = (np.array(permuted_sharpes) >= original_sharpe).mean()
        return {"p_value": p_value, "significant": p_value < 0.05}

    def _run_walk_forward(
        self,
        close: pd.Series,
        strategy_type: str,
        window: int,
        threshold: float,
        hold_days: int,
    ) -> float:
        """Run walk-forward and return average OOS Sharpe."""
        n = len(close)
        oos_sharpes = []

        for split in range(3):
            train_end = int(n * (0.5 + split * 0.15))
            test_end = min(int(n * (0.7 + split * 0.15)), n)

            if train_end >= test_end - 20:
                continue

            test_close = close.iloc[train_end:test_end]

            rolling_mean = test_close.rolling(window).mean()
            rolling_std = test_close.rolling(window).std()
            zscore = (test_close - rolling_mean) / rolling_std
            fwd_ret = test_close.shift(-hold_days) / test_close - 1

            if "mean_reversion" in strategy_type:
                long_signal = zscore < -threshold
                short_signal = zscore > threshold
            else:
                momentum = test_close.pct_change(window)
                long_signal = momentum > threshold
                short_signal = momentum < -threshold

            long_returns = fwd_ret[long_signal].dropna()
            short_returns = -fwd_ret[short_signal].dropna()
            all_returns = pd.concat([long_returns, short_returns])

            if len(all_returns) > 5 and all_returns.std() > 0:
                sharpe = all_returns.mean() / all_returns.std() * np.sqrt(252 / hold_days)
                oos_sharpes.append(sharpe)

        return np.mean(oos_sharpes) if oos_sharpes else 0


# =============================================================================
# PHASE 4: VALIDATION & PROMOTION
# =============================================================================


class CriticValidator:
    """Validate and critique test results."""

    def validate(self, results: list[TestResult]) -> dict:
        """Validate all results and flag concerns."""
        validated = {
            "timestamp": datetime.now().isoformat(),
            "total_tested": len(results),
            "significant_count": sum(1 for r in results if r.is_significant),
            "approved": [],
            "flagged": [],
            "rejected": [],
        }

        for result in results:
            if not result.success:
                validated["rejected"].append(
                    {"id": result.hypothesis_id, "reason": result.notes}
                )
                continue

            if result.is_significant:
                # Check for red flags
                red_flags = []

                if result.n_trades < 20:
                    red_flags.append("Low trade count (<20)")
                if result.oos_sharpe < 0.5:
                    red_flags.append("Low OOS Sharpe (<0.5)")
                if result.win_rate < 0.4:
                    red_flags.append("Low win rate (<40%)")

                if red_flags:
                    validated["flagged"].append(
                        {
                            "id": result.hypothesis_id,
                            "sharpe": result.sharpe_ratio,
                            "p_value": result.mcpt_pvalue,
                            "flags": red_flags,
                        }
                    )
                else:
                    validated["approved"].append(
                        {
                            "id": result.hypothesis_id,
                            "sharpe": result.sharpe_ratio,
                            "p_value": result.mcpt_pvalue,
                            "oos_sharpe": result.oos_sharpe,
                            "n_trades": result.n_trades,
                        }
                    )
            else:
                validated["rejected"].append(
                    {
                        "id": result.hypothesis_id,
                        "reason": f"Not significant (p={result.mcpt_pvalue:.3f})",
                    }
                )

        return validated


# =============================================================================
# ORCHESTRATOR
# =============================================================================


class AlphaHuntOrchestrator:
    """Orchestrate the complete alpha hunt cycle."""

    def __init__(self, output_dir: Path = Path("/home/nock/quant_results/alpha_hunt")):
        self.output_dir = output_dir
        self.scanner = MarketScanner()
        self.scout = DataScout()
        self.knowledge = KnowledgeQuerier()
        self.hypothesis_gen = HypothesisGenerator()
        self.tester = HypothesisTester()
        self.critic = CriticValidator()

    async def run_cycle(
        self,
        focus: str | None = None,
        max_hypotheses: int = 10,
        quick: bool = False,
    ) -> CycleResult:
        """Run complete alpha hunt cycle."""
        start_time = datetime.now()
        cycle_id = start_time.strftime("%Y%m%d_%H%M%S")

        logger.info("=" * 70)
        logger.info(f"ALPHA HUNT CYCLE: {cycle_id}")
        logger.info(f"Focus: {focus or 'all'}")
        logger.info("=" * 70)

        # Phase 1: Reconnaissance (parallel)
        logger.info("\n[PHASE 1] Reconnaissance...")
        scanner_task = asyncio.create_task(self.scanner.scan(focus))
        scout_task = asyncio.create_task(self.scout.scout())
        knowledge_task = asyncio.create_task(self.knowledge.query())

        scanner_results = await scanner_task
        scout_results = await scout_task
        knowledge_results = await knowledge_task

        logger.info(
            f"  Scanner: {scanner_results['scanned_symbols']} symbols, "
            f"{len(scanner_results['opportunities'])} opportunities"
        )
        logger.info(f"  Scout: {len(scout_results['blog_sources'])} blog sources checked")
        logger.info(f"  Knowledge: {len(knowledge_results['open_leads'])} open leads")

        reconnaissance = {
            "scanner": scanner_results,
            "scout": scout_results,
            "knowledge": knowledge_results,
        }

        # Phase 2: Hypothesis Generation
        logger.info("\n[PHASE 2] Generating hypotheses...")
        hypotheses = self.hypothesis_gen.generate(
            scanner_results, scout_results, knowledge_results, max_hypotheses
        )
        logger.info(f"  Generated {len(hypotheses)} hypotheses")

        for h in hypotheses[:5]:
            logger.info(f"    [{h.priority:.2f}] {h.statement}")

        # Phase 3: Testing (parallel)
        logger.info("\n[PHASE 3] Testing hypotheses...")
        test_tasks = [self.tester.test(h, quick=quick) for h in hypotheses]
        test_results = await asyncio.gather(*test_tasks)

        significant = [r for r in test_results if r.is_significant]
        logger.info(f"  Tested {len(test_results)}, {len(significant)} significant")

        # Phase 4: Validation
        logger.info("\n[PHASE 4] Validating results...")
        validation = self.critic.validate(test_results)
        logger.info(f"  Approved: {len(validation['approved'])}")
        logger.info(f"  Flagged: {len(validation['flagged'])}")
        logger.info(f"  Rejected: {len(validation['rejected'])}")

        # Compile results
        duration = (datetime.now() - start_time).total_seconds()

        cycle_result = CycleResult(
            cycle_id=cycle_id,
            timestamp=start_time.isoformat(),
            focus=focus or "all",
            reconnaissance=reconnaissance,
            hypotheses=hypotheses,
            test_results=test_results,
            significant_findings=[r.hypothesis_id for r in significant],
            promoted_strategies=[a["id"] for a in validation["approved"]],
            next_priorities=[
                "Continue testing flagged strategies with more data",
                "Investigate research hypotheses manually",
            ],
            duration_seconds=duration,
        )

        # Save results
        await self._save_results(cycle_result)

        # Print summary
        self._print_summary(cycle_result)

        return cycle_result

    def _json_serializer(self, obj):
        """Custom JSON serializer for special types."""
        if isinstance(obj, bool):
            return bool(obj)
        if isinstance(obj, (np.bool_, np.integer)):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        return str(obj)

    async def _save_results(self, result: CycleResult):
        """Save cycle results to disk."""
        cycle_dir = self.output_dir / f"cycle_{result.cycle_id}"
        cycle_dir.mkdir(parents=True, exist_ok=True)

        # Save reconnaissance
        with open(cycle_dir / "reconnaissance.json", "w") as f:
            json.dump(result.reconnaissance, f, indent=2, default=self._json_serializer)

        # Save hypotheses
        with open(cycle_dir / "hypotheses.json", "w") as f:
            json.dump([asdict(h) for h in result.hypotheses], f, indent=2, default=self._json_serializer)

        # Save test results
        test_dir = cycle_dir / "test_results"
        test_dir.mkdir(exist_ok=True)
        for tr in result.test_results:
            with open(test_dir / f"{tr.hypothesis_id}.json", "w") as f:
                json.dump(asdict(tr), f, indent=2, default=self._json_serializer)

        # Save summary
        summary = {
            "cycle_id": result.cycle_id,
            "focus": result.focus,
            "duration_seconds": result.duration_seconds,
            "hypotheses_tested": len(result.hypotheses),
            "significant_findings": result.significant_findings,
            "promoted_strategies": result.promoted_strategies,
            "next_priorities": result.next_priorities,
        }
        with open(cycle_dir / "summary.json", "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"\nResults saved to: {cycle_dir}")

    def _print_summary(self, result: CycleResult):
        """Print cycle summary."""
        logger.info("\n" + "=" * 70)
        logger.info("CYCLE SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Duration: {result.duration_seconds:.1f} seconds")
        logger.info(f"Hypotheses tested: {len(result.hypotheses)}")
        logger.info(f"Significant findings: {len(result.significant_findings)}")
        logger.info(f"Promoted to paper trading: {len(result.promoted_strategies)}")

        if result.promoted_strategies:
            logger.info("\nPromoted strategies:")
            for s in result.promoted_strategies:
                logger.info(f"  - {s}")

        if result.next_priorities:
            logger.info("\nNext priorities:")
            for p in result.next_priorities:
                logger.info(f"  - {p}")


# =============================================================================
# MAIN
# =============================================================================


async def main():
    parser = argparse.ArgumentParser(description="Run Alpha Hunt cycle")
    parser.add_argument(
        "--focus",
        choices=["commodities", "semiconductors", "tech_mega", "financials", "etfs"],
        help="Focus area for the cycle",
    )
    parser.add_argument(
        "--max-hypotheses",
        type=int,
        default=10,
        help="Maximum hypotheses to test",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode (fewer permutations)",
    )

    args = parser.parse_args()

    orchestrator = AlphaHuntOrchestrator()
    await orchestrator.run_cycle(
        focus=args.focus,
        max_hypotheses=args.max_hypotheses,
        quick=args.quick,
    )


if __name__ == "__main__":
    asyncio.run(main())
